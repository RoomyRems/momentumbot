from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from momentumbot.research import identity_coverage as m
from tests.test_census_scanner_bridge import row, coverage
from tests.test_coverage_continuation import actions as action_reply

ROOT = Path(__file__).resolve().parents[1]
EARLY, LATE = m.DATES[:2]
BAR = {'o': 2, 'h': 3, 'l': 1, 'c': 2.5, 'v': 500, 'n': 10, 'vw': 2.2}


def packet(rows, day=EARLY, records=None):
    ref = m.b.project_date(rows, day)
    data = {'trading_date': day, 'reference_sha256': ref['content_sha256'],
        'records': records if records is not None else {s: coverage() for s in ref['coverage_symbols']}}
    return m.seal({'coverage': data, 'coverage_sha256': m.fingerprint(data)})


def bound(rows, day=EARLY, records=None):
    return m.bind_day(rows, day, packet(rows, day, records))


def source_actions(day=LATE, events=None):
    state = m.capture.ActionPages(m.capture.old.daily.identity_requests(day)[0])
    request = state.request()
    state.accept(request, action_reply(events or []))
    result = state.result()
    rows = result.pop('rows')
    result.pop('content_sha256')
    return {'root': state.root, 'rows': rows,
        'source_result': m.seal({**result, 'row_count': len(rows), 'rows_sha256': m.fingerprint(rows)}),
        'lineage': [{'body_sha256': p['body_sha256'], 'request_sha256': p['request_sha256']}
            for p in result['pages']]}


def evidence(day=LATE, events=None):
    return m.action_evidence(source_actions(day, events), [], day)


def view(symbol='OLD', asof=EARLY, target=EARLY, status='captured_bar'):
    return {'symbol': symbol, 'asof': asof, 'target_date': target, 'status': status,
        'bar': deepcopy(BAR) if status == 'captured_bar' else None,
        'source_members': [] if status == 'request_not_captured' else [{'body_sha256': 'a' * 64}]}


def lookup(symbol, asof, target):
    return view(symbol, asof, target, 'request_not_captured' if asof < target else 'captured_bar')


def pair():
    return m.continuity_pair(bound([row('OLD')]), bound([row('NEW')], LATE), evidence(), lookup)


class DatedMembershipTests(unittest.TestCase):
    def test_exact_existing_membership_and_no_runtime_promotion(self):
        rows = [row('VALID'), row('UNIDENTIFIED', cik='', composite_figi='')]
        original = m.b.bind_coverage(rows, EARLY, packet(rows)['coverage'],
            expected_coverage_sha256=packet(rows)['coverage_sha256'])
        result = bound(rows)
        self.assertEqual(result['membership'], original['membership'])
        self.assertEqual(result['identity_quarantine'], original['identity_statuses']['quarantined'])
        self.assertTrue(result['same_date_membership_recomputed'])
        for key in ('historical_scanner_enabled', 'identity_continuity_verified',
                    'later_identity_evidence_changes_earlier_membership'):
            self.assertFalse(result[key])

    def test_post_coverage_unique_cik_and_explicit_failure(self):
        rows = [row('VALID', composite_figi=''), row('ABSENT', composite_figi='')]
        records = {'VALID': coverage(), 'ABSENT': coverage(raw_target_session_present=False,
            split_target_session_present=False, coverage_pass=False)}
        result = bound(rows, records=records)
        self.assertEqual([r['ticker'] for r in result['membership']], ['VALID'])
        self.assertEqual(result['identity_kind_counts'], {'unique_cik_fallback': 1})
        self.assertEqual(result['coverage_failures'], {'ABSENT': records['ABSENT']})

    def test_duplicate_figi_is_visible_without_new_exclusion_rule(self):
        result = bound([row('ONE'), row('TWO')])
        self.assertEqual(len(result['membership']), 2)
        self.assertEqual(result['duplicate_identifier_groups'],
            [{'kind': 'composite_figi', 'identifier': 'FIGI1', 'tickers': ['ONE', 'TWO']}])

    def test_missing_coverage_not_replaced_by_false_or_other_date(self):
        rows = [row()]
        for data in (packet(rows, records={}), packet(rows, LATE)):
            with self.subTest(data=data), self.assertRaises(ValueError): m.bind_day(rows, EARLY, data)

    def test_forged_coverage_and_retrospective_reference_fields_rejected(self):
        data = packet([row()])
        data['coverage']['records']['SYNTHETIC']['coverage_pass'] = False
        with self.assertRaises(ValueError): m.bind_day([row()], EARLY, data)
        for key in ('ross_fill', 'pnl', 'future_return'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.bind_day([{**row(), key: 1}], EARLY, packet([row()]))


class ActionEvidenceTests(unittest.TestCase):
    def test_original_order_all_rows_and_symbol_only_relevance_preserved(self):
        events = [{'id': 'last', 'process_date': LATE, 'old_symbol': 'OLD', 'new_symbol': 'NEW'},
            {'id': 'first', 'process_date': EARLY},
            {'id': 'other', 'process_date': EARLY, 'old_symbol': 'UNRELATED', 'new_symbol': 'ELSE'}]
        source = source_actions(events=events)
        original = deepcopy(source)
        out = m.action_evidence(source, [{'ticker': 'NEW'}], LATE)
        self.assertEqual(source, original)
        self.assertEqual([r['id'] for r in out['rows']], ['last', 'first', 'other'])
        self.assertEqual(out['membership_action_row_indices'], {'NEW': [0]})
        self.assertEqual(out['rows_without_parsable_symbol'], [1])
        self.assertFalse(out['as_known_historical_feed'])
        self.assertFalse(out['symbol_match_proves_same_security'])
        self.assertFalse(out['historical_adjustment_factor_applied'])

    def test_rows_lineage_and_date_cannot_be_relabelled(self):
        source = source_actions(events=[{'id': 'event', 'process_date': LATE}])
        bad = deepcopy(source)
        bad['rows'][0]['process_date'] = '2030-01-01'
        with self.assertRaises(ValueError): m.action_evidence(bad, [], LATE)
        bad = deepcopy(source)
        bad['lineage'][0]['body_sha256'] = '0' * 64
        with self.assertRaises(ValueError): m.action_evidence(bad, [], LATE)
        with self.assertRaises(ValueError): m.action_evidence(source, [], EARLY)


class AliasAndContinuityTests(unittest.TestCase):
    def test_four_separate_asof_queries_and_no_mutation(self):
        before, after = bound([row('OLD')]), bound([row('NEW')], LATE)
        saved = deepcopy(before)
        out = m.continuity_pair(before, after, evidence(), lookup)
        self.assertEqual(before, saved)
        check = out['alias_checks'][0]
        self.assertEqual([(v['symbol'], v['asof'], v['target_date']) for v in check['views']],
            [('OLD', EARLY, EARLY), ('NEW', LATE, EARLY), ('OLD', EARLY, LATE), ('NEW', LATE, LATE)])
        self.assertTrue(check['earlier_date_comparison']['match'])
        self.assertFalse(check['bidirectional_match'])
        self.assertFalse(out['identity_continuity_verified'])

    def test_same_ticker_different_figi_is_not_merged_by_shared_cik(self):
        out = m.continuity_pair(bound([row('SAME')]), bound([row('SAME', composite_figi='OTHER')], LATE), evidence(), lookup)
        self.assertEqual(out['changed_transitions'], [])
        self.assertEqual(len(out['same_ticker_different_figi']), 1)

    def test_all_seven_bar_fields_participate(self):
        for key in m.BAR_FIELDS:
            other = view()
            other['bar'][key] += 1
            with self.subTest(key=key):
                self.assertEqual(m.compare_views(view(), other), {'match': False, 'status': key + '_mismatch'})
        self.assertTrue(m.compare_views(view(), view())['match'])

    def test_invalid_bar_cannot_hide_behind_missing_or_mismatch(self):
        for value in (float('nan'), float('inf'), True, -1, '2'):
            wrong = view()
            wrong['bar']['vw'] = value
            wrong['bar']['o'] = 99
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.compare_views(view(status='request_not_captured'), wrong)

    def test_absent_bars_need_explicit_consistent_status(self):
        for status in ('captured_empty', 'request_not_captured'):
            wrong = view(status=status)
            wrong['bar'] = deepcopy(BAR)
            with self.subTest(status=status), self.assertRaises(ValueError): m.compare_views(view(), wrong)
        wrong = view()
        wrong['source_members'] = []
        with self.assertRaises(ValueError): m.compare_views(view(), wrong)

    def test_asof_target_and_source_dates_cannot_be_swapped(self):
        def wrong_lookup(symbol, asof, target): return view(symbol, LATE, target)
        with self.assertRaises(ValueError):
            m.continuity_pair(bound([row('OLD')]), bound([row('NEW')], LATE), evidence(), wrong_lookup)
        with self.assertRaises(ValueError): m.compare_views(view(), view(target=LATE))
        with self.assertRaises(ValueError):
            m.continuity_pair(bound([row('OLD')]), bound([row('NEW')], m.DATES[2]), evidence(), lookup)
        with self.assertRaises(ValueError):
            m.continuity_pair(bound([row('OLD')]), bound([row('NEW')], LATE), evidence(EARLY), lookup)

    def test_name_change_path_does_not_replace_missing_alias_bars(self):
        events = [{'id': 'name', 'old_symbol': 'OLD', 'new_symbol': 'NEW', 'process_date': LATE}]
        out = m.continuity_pair(bound([row('OLD')]), bound([row('NEW')], LATE), evidence(events=events), lookup)
        record = out['name_change_resolution']['records'][0]
        self.assertTrue(record['name_change_path_found'])
        self.assertFalse(record['snapshot_window_safe'])
        self.assertEqual(record['resolution'], 'unresolved_snapshot_window_alias_gap')

    def test_both_comparison_dates_required_for_match(self):
        def all_views(symbol, asof, target): return view(symbol, asof, target)
        out = m.continuity_pair(bound([row('OLD')]), bound([row('NEW')], LATE), evidence(), all_views)
        self.assertTrue(out['alias_checks'][0]['bidirectional_match'])
        self.assertTrue(out['name_change_resolution']['records'][0]['snapshot_window_safe'])
        self.assertFalse(out['identity_continuity_verified'])

    def test_resealed_changed_pair_cannot_authorize_different_plan_scope(self):
        out = pair()
        out['alias_checks'][0]['views'][2]['asof'] = '2030-01-01'
        out = m.seal({k: v for k, v in out.items() if k != 'content_sha256'})
        with self.assertRaises((ValueError, StopIteration)): m.remaining_alias_requests([out])

    def test_remaining_plan_reuses_three_views_deduplicates_and_stays_unarmed(self):
        out = pair()
        plan = m.remaining_alias_requests([out, out])
        self.assertEqual(plan['missing_view_count'], 1)
        self.assertEqual(plan['initial_request_count'], 1)
        self.assertEqual(plan['maximum_requests_if_separately_captured'], 10)
        root = plan['roots'][0]
        self.assertEqual(root['params']['symbols'], 'OLD')
        self.assertEqual(root['params']['asof'], EARLY)
        self.assertEqual(root['comparison_date'], LATE)
        self.assertEqual(root['params']['adjustment'], 'raw')
        self.assertEqual(plan['authorized_provider_calls_now'], 0)
        self.assertFalse(plan['automatic_retry'])

    def test_captured_empty_view_is_not_a_new_request(self):
        def empty_lookup(symbol, asof, target): return view(symbol, asof, target, 'captured_empty')
        out = m.continuity_pair(bound([row('OLD')]), bound([row('NEW')], LATE), evidence(), empty_lookup)
        self.assertFalse(out['alias_checks'][0]['bidirectional_match'])
        self.assertEqual(m.remaining_alias_requests([out])['roots'], [])


class SourcePinsTests(unittest.TestCase):
    def test_changed_bytes_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'original'
            path.write_bytes(b'original')
            pin = {'bytes': 8, 'sha256': m.sha(b'original')}
            self.assertEqual(m._pinned_file(path, pin), path)
            link = Path(tmp) / 'link'
            link.symlink_to(path)
            with self.assertRaises(ValueError): m._pinned_file(link, pin)
            path.write_bytes(b'changed!')
            with self.assertRaises(ValueError): m._pinned_file(path, pin)

    def test_wrong_capture_rejected_before_archive_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fake.zip'
            path.write_bytes(b'fake')
            with self.assertRaises(ValueError): m.CoverageArchive(path, ROOT)

    def test_frozen_registration_and_ancestor_unchanged(self):
        contract = m.validate_registration(ROOT)
        self.assertEqual(contract['parent_commit'], m.PARENT)
        self.assertEqual(contract['selected_dates'], list(m.DATES))
        self.assertFalse(contract['changes_strategy_or_risk'])
        self.assertEqual(contract['provider_calls_authorized_now'], 0)
        with patch.object(m, 'CAPTURE_PIN', {**m.CAPTURE_PIN, 'sha256': '0' * 64}):
            with self.assertRaises(ValueError): m.validate_registration(ROOT)


if __name__ == '__main__': unittest.main()
