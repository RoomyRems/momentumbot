from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from momentumbot.providers.massive import normalize_reference_tickers
from momentumbot.historical_universe import classify_ticker_group
from momentumbot.research import census_scanner_bridge as m

ROOT = Path(__file__).resolve().parents[1]
DAY = m.DATES[0]


def row(ticker='SYNTHETIC', **changes):
    value = {'ticker': ticker, 'type': 'CS', 'name': 'Synthetic Company Common Stock',
        'primary_exchange': 'XNAS', 'cik': '123', 'composite_figi': 'FIGI1',
        'active': True, 'market': 'stocks', 'locale': 'us'}
    value.update(changes)
    return normalize_reference_tickers([value])[0]


def coverage(**changes):
    value = {k: k != 'invalid_symbol' for k in m.COVERAGE_FIELDS}
    value.update(changes)
    return value


class ReferenceTests(unittest.TestCase):
    def project(self, rows): return m.project_date(rows, DAY)

    def test_no_fabricated_coverage(self):
        out = self.project([row()])
        self.assertEqual(out['decisions'], [classify_ticker_group([row()], None).payload()])
        self.assertFalse(out['decisions'][0]['included'])
        self.assertEqual(out['coverage_symbols'], ['SYNTHETIC'])
        self.assertFalse(out['historical_scanner_enabled'])
        self.assertFalse(out['identity_continuity_verified'])

    def test_collision_uses_frozen_semantics(self):
        rows = [row(), row(type='PFD', name='Synthetic Preferred Stock', composite_figi='OTHER')]
        out = self.project(rows)
        self.assertEqual(out['coverage_symbols'], ['SYNTHETIC'])
        self.assertEqual(out['decisions'][0]['accepted_identity_count'], 1)
        self.assertEqual(out['source_row_count'], 2)
        self.assertEqual(len(out['reference_exceptions'][0]['records']), 2)

    def test_two_common_identities_not_merged(self):
        out = self.project([row(), row(composite_figi='OTHER')])
        self.assertEqual(out['coverage_symbols'], [])
        self.assertEqual(out['decisions'][0]['reason'], 'multiple_semantically_eligible_identities')

    def test_common_type_name_conflicts_retained(self):
        for name in ('Synthetic Preferred Stock', 'Synthetic Notes due 2040', 'Synthetic Warrants'):
            with self.subTest(name=name):
                out = self.project([row(name=name)])
                self.assertEqual(out['coverage_symbols'], [])
                self.assertEqual(out['decisions'][0]['reason'], 'instrument_metadata_conflict')

    def test_missing_type_not_inferred_from_name_or_other_dates(self):
        out = self.project([row(type='')])
        self.assertEqual(out['coverage_symbols'], [])
        self.assertTrue(out['reference_exceptions'][0]['missing_type'])
        self.assertFalse(out['historical_identity_resolved'])

    def test_missing_figi_unique_cik_is_only_provisional(self):
        out = self.project([row(composite_figi='')])
        self.assertEqual(out['reference_identity_counts'], {'unique_cik_fallback': 1})
        self.assertTrue(out['reference_identity_is_provisional'])
        self.assertFalse(out['historical_identity_resolved'])

    def test_missing_cik_with_figi_accepted_by_existing_rule(self):
        out = self.project([row(cik='')])
        self.assertEqual(out['reference_identity_counts'], {'composite_figi': 1})

    def test_nonunique_cik_not_used_as_security_identity(self):
        out = self.project([row('SYNTHETICA', composite_figi=''), row('SYNTHETICB', composite_figi='')])
        self.assertEqual(out['identity_quarantine_count'], 2)
        self.assertEqual(len(out['coverage_symbols']), 2)  # no circular precoverage identity filter

    def test_missing_identifiers_quarantined_without_dropping_source(self):
        out = self.project([row(composite_figi='', cik='')])
        self.assertEqual(out['identity_quarantine_count'], 1)
        self.assertEqual(out['ticker_count'], 1)
        self.assertEqual(out['coverage_symbols'], ['SYNTHETIC'])

    def test_duplicate_reference_identity_rejected(self):
        with self.assertRaises(ValueError): self.project([row(), row()])

    def test_future_label_and_price_fields_rejected(self):
        for key in ('price', 'pnl', 'ross_fill', 'future_return'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.project([{**row(), key: 1}])

    def test_wrong_scope_and_scalar_types_rejected(self):
        for key, val in [('active', False), ('active', 'true'), ('market', 'crypto'),
                         ('locale', 'gb'), ('cik', 123), ('name', None)]:
            with self.subTest(key=key, val=val), self.assertRaises(ValueError):
                self.project([{**row(), key: val}])

    def test_no_empty_source_or_replacement_dates(self):
        with self.assertRaises(ValueError): self.project([])
        with self.assertRaises(ValueError): m.project_date([row()], '2025-01-02')

    def test_input_not_modified(self):
        rows = [row('SYNTHETICB'), row('SYNTHETICA', composite_figi='OTHER')]
        saved = deepcopy(rows)
        out = self.project(rows)
        self.assertEqual(rows, saved)
        self.assertEqual(out['coverage_symbols'], ['SYNTHETICA', 'SYNTHETICB'])


class CoverageTests(unittest.TestCase):
    def bind(self, rows, records):
        packet = {'trading_date': DAY, 'reference_sha256': m.project_date(rows, DAY)['content_sha256'],
            'records': records}
        return m.bind_coverage(rows, DAY, packet, expected_coverage_sha256=m.fingerprint(packet))

    def test_wrong_coverage_date_or_reference_cannot_be_resealed(self):
        packet = {'trading_date': DAY, 'reference_sha256': m.project_date([row()], DAY)['content_sha256'],
            'records': {'SYNTHETIC': coverage()}}
        for key, val in [('trading_date', m.DATES[1]), ('reference_sha256', '0' * 64)]:
            wrong = {**packet, key: val}
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.bind_coverage([row()], DAY, wrong, expected_coverage_sha256=m.fingerprint(wrong))

    def test_coverage_requires_dated_envelope(self):
        old = {'SYNTHETIC': coverage()}
        with self.assertRaises(ValueError):
            m.bind_coverage([row()], DAY, old, expected_coverage_sha256=m.fingerprint(old))

    def test_exact_existing_membership_projection(self):
        records = {'SYNTHETIC': coverage()}
        out = self.bind([row()], records)
        self.assertEqual(out['decisions'], [classify_ticker_group([row()], records['SYNTHETIC']).payload()])
        self.assertEqual(out['membership_symbols'], ['SYNTHETIC'])
        self.assertEqual(out['membership'][0]['identity_identifier'], 'FIGI1')
        self.assertFalse(out['provider_coverage_origin_authenticated'])
        self.assertFalse(out['historical_scanner_enabled'])

    def test_complete_exact_coverage_population(self):
        for records in ({}, {'OTHER': coverage()}, {'SYNTHETIC': coverage(), 'OTHER': coverage()}):
            with self.subTest(records=records), self.assertRaises(ValueError): self.bind([row()], records)

    def test_coverage_projection_tamper_rejected(self):
        with self.assertRaises(ValueError):
            m.bind_coverage([row()], DAY, {'SYNTHETIC': coverage()}, expected_coverage_sha256='0' * 64)

    def test_missing_and_false_are_different(self):
        out = self.bind([row()], {'SYNTHETIC': coverage(raw_target_session_present=False,
            split_target_session_present=False, coverage_pass=False)})
        self.assertEqual(out['membership_symbols'], [])
        self.assertEqual(out['decisions'][0]['reason'], 'missing_target_session')

    def test_raw_split_disagreement_retained(self):
        out = self.bind([row()], {'SYNTHETIC': coverage(raw_target_session_present=False, coverage_pass=False)})
        self.assertEqual(out['decisions'][0]['reason'], 'raw_split_coverage_mismatch')

    def test_coverage_observations_cannot_coerce_or_contradict(self):
        bad = [coverage(coverage_pass='true'), coverage(invalid_symbol=1),
               coverage(raw_target_session_present=False), coverage(extra=False)]
        for record in bad:
            with self.subTest(record=record), self.assertRaises(ValueError): self.bind([row()], {'SYNTHETIC': record})

    def test_cik_uniqueness_recomputed_after_coverage(self):
        rows = [row('SYNTHETICA', composite_figi=''), row('SYNTHETICB', composite_figi='')]
        out = self.bind(rows, {'SYNTHETICA': coverage(), 'SYNTHETICB': coverage(invalid_symbol=True, coverage_pass=False)})
        self.assertEqual(out['membership_symbols'], ['SYNTHETICA'])
        self.assertEqual(out['membership'][0]['identity_identifier_kind'], 'unique_cik_fallback')

    def test_metadata_exclusions_cannot_be_resurrected_by_coverage(self):
        rows = [row(type='PFD')]
        self.assertEqual(self.bind(rows, {})['membership_symbols'], [])
        with self.assertRaises(ValueError): self.bind(rows, {'SYNTHETIC': coverage()})


class PlanAndPinsTests(unittest.TestCase):
    def test_request_union_all_candidates_and_adjustments(self):
        rows = [row(f'SYNTHETIC{i:04d}', composite_figi=f'FIGI{i}') for i in range(251)]
        ref = m.project_date(rows, DAY)
        requests = m.coverage_requests(ref)
        self.assertEqual(len(requests), 4)
        for adjustment in ('raw', 'split'):
            selected = [r for r in requests if r['params']['adjustment'] == adjustment]
            self.assertEqual([s for r in selected for s in r['params']['symbols'].split(',')], ref['coverage_symbols'])
            self.assertEqual(selected[0]['params']['asof'], DAY)
            self.assertEqual(selected[0]['params']['start'], '2026-02-18T00:00:00+00:00')
            self.assertEqual(selected[0]['params']['end'], '2026-03-05T00:00:00+00:00')

    def test_dst_uses_inherited_utc_window_not_new_semantics(self):
        day = '2026-03-09'
        params = m.coverage_requests(m.project_date([row()], day))[0]['params']
        self.assertEqual(params['start'], '2026-02-23T00:00:00+00:00')
        self.assertEqual(params['end'], '2026-03-10T00:00:00+00:00')

    def test_no_requests_for_metadata_exclusions(self):
        self.assertEqual(m.coverage_requests(m.project_date([row(type='ETF')], DAY)), [])

    def test_wrong_archive_cannot_be_admitted_by_self_supplied_pins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fake.zip'
            path.write_bytes(b'fake')
            with self.assertRaises(ValueError): m.CensusArchive(path, ROOT)

    def test_symlink_cannot_substitute_original_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fake.zip'
            path.write_bytes(b'fake')
            link = Path(tmp) / 'link.zip'
            link.symlink_to(path)
            with self.assertRaises(ValueError): m.CensusArchive(link, ROOT)

    def test_frozen_registration_and_source_authority(self):
        contract = m.validate_registration(ROOT)
        self.assertEqual(contract['parent_commit'], m.PARENT)
        self.assertEqual(contract['provider_calls_authorized_now'], 0)
        self.assertFalse(contract['historical_scanner_enabled'])


if __name__ == '__main__': unittest.main()
