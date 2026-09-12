from copy import deepcopy
from itertools import permutations
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from momentumbot.research import census_order_repair as m
from momentumbot.research import census_payload_evidence as evidence
from tests.test_early_pullback_census_v01 import body, row, synthetic_reply, SECRET

ROOT = Path(__file__).resolve().parents[1]


def feed(state, raw):
    request = state.next_request()
    projected = m.project_body(request, raw)
    state.accept(request, m.sha(raw), projected)
    return projected


def initialized():
    state = m.CensusState()
    feed(state, synthetic_reply(state.next_request(), SECRET)['body'])
    return state


class CensusOrderRepairTests(unittest.TestCase):
    def setUp(self):
        self.request = m.diagnostic.request()

    def test_frozen_registration_has_no_capture_or_runtime_authority(self):
        contract = m.validate_registration(ROOT)
        self.assertEqual(contract['selected_dates'], list(m.legacy.DATES))
        self.assertEqual(contract['limits'], m.legacy.limits())
        self.assertEqual(contract['parent_commit'], evidence.CODE)
        for key, value in m.legacy.BOUNDARY.items():
            self.assertEqual(contract[key], value)

    def test_original_artifact_chain_and_rejected_body_reproduce(self):
        audit, raw = evidence.verify(ROOT)
        self.assertEqual(audit['attempts'], 1)
        self.assertEqual(len(audit['false_regressions']), 11)
        self.assertFalse(audit['old_rejected_body_byte_identical_claim'])
        with self.assertRaisesRegex(ValueError, 'provider page order regressed'):
            m.legacy.project_body(self.request, raw)
        repaired = m.project_body(self.request, raw)
        self.assertEqual(repaired['raw_row_count'], 1000)
        self.assertEqual(repaired['rows'], list(m.legacy.normalize_reference_tickers(
            m.legacy.parse_json(raw)['results'])))
        self.assertEqual(repaired['provider_tickers'][124:126], ['ACRV', 'ACRpC'])
        self.assertEqual(m.sha(raw), evidence.BODY_PIN)

    def test_actual_page_replays_with_original_hash_and_cursor(self):
        _, raw = evidence.verify(ROOT)
        state = initialized()
        feed(state, raw)
        self.assertEqual(state.summary()[0]['accepted_rows'], 1000)
        self.assertEqual(state.last_provider_ticker[m.legacy.DATES[0]], 'BAIV')
        following = state.next_request()
        self.assertEqual(following['page'], 2)
        self.assertEqual(following['predecessor_response_sha256'], evidence.BODY_PIN)
        self.assertEqual(following['root_query'], self.request['root_query'])
        self.assertNotEqual(following['predecessor_response_sha256'], m.sha(m.legacy.render(
            m.project_body(self.request, raw))))

    def test_native_order_is_validated_before_any_sorting(self):
        for tickers in permutations(('ACRV', 'ACRpC', 'ADCT')):
            raw = body([row(t) for t in tickers])
            if list(tickers) == sorted(tickers):
                self.assertEqual(m.project_body(self.request, raw)['provider_tickers'], list(tickers))
            else:
                with self.assertRaisesRegex(ValueError, 'provider page order regressed'):
                    m.project_body(self.request, raw)

    def test_uppercase_cannot_hide_a_real_within_page_regression(self):
        raw = body([row('ACRpC'), row('ACRV')])
        self.assertEqual(m.legacy.project_body(self.request, raw)['raw_row_count'], 2)
        with self.assertRaisesRegex(ValueError, 'provider page order regressed'):
            m.project_body(self.request, raw)

    def test_projection_preserves_raw_case_and_canonical_identity(self):
        raw = body([row('ACRV'), row('ACRpC')])
        self.assertEqual(m.project_body(self.request, raw)['provider_tickers'], ['ACRV', 'ACRpC'])
        self.assertEqual([r['ticker'] for r in m.project_body(self.request, raw)['rows']], ['ACRPC', 'ACRV'])

    def test_unchanged_type_dictionary_and_uppercase_projections(self):
        request = m.legacy.type_request()
        raw = synthetic_reply(request, SECRET)['body']
        self.assertEqual(m.project_body(request, raw), m.legacy.project_body(request, raw))
        for rows in ([], [row('AAA')], [row('AAA'), row('ZZZ')], [row('AAA', name='naïve')]):
            raw = body(rows)
            projected = m.project_body(self.request, raw)
            self.assertEqual({k: v for k, v in projected.items() if k != 'provider_tickers'},
                m.legacy.project_body(self.request, raw))

    def test_schema_filter_count_and_metadata_checks_are_not_bypassed(self):
        valid = m.legacy.parse_json(body([row('ACRV'), row('ACRpC')]))
        cases = [dict(valid, status='ERROR'), dict(valid, unknown='x'), dict(valid, count=1),
            dict(valid, count=True), dict(valid, results={}), dict(valid, results=[True]),
            dict(valid, results=[row('AAA', unexpected='x')]),
            dict(valid, count=1, results=[dict(row('AAA'), active=False)]),
            dict(valid, count=1, results=[dict(row('AAA'), market='crypto')]),
            dict(valid, count=1, results=[dict(row('AAA'), locale='global')]),
            dict(valid, count=1, results=[row('AAA', name=7)]),
            dict(valid, count=1, results=[row('AAA', name='bad\ntext')]),
            dict(valid, count=1, results=[row('AAA', name='x' * 2049)])]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                m.project_body(self.request, m.legacy.render(case))

    def test_ticker_is_required_string_not_coerced(self):
        for ticker in (None, '', ' ', 7, False, [], 'bad\ntext', '\ud800', 'x' * 2049):
            with self.subTest(ticker=ticker), self.assertRaises(ValueError):
                m.project_body(self.request, body([row(ticker)]))

    def test_duplicate_keys_nonfinite_json_and_nonobject_root_still_rejected(self):
        for raw in (b'{"status":"OK","status":"OK","results":[]}',
            b'{"status":"OK","results":[],"count":NaN}', b'[]', b'not-json'):
            with self.assertRaises(ValueError):
                m.project_body(self.request, raw)

    def test_cursor_host_query_credentials_and_duplicates_still_rejected(self):
        for url in ('https://api.polygon.io/v3/reference/tickers?cursor=x',
            'https://api.massive.com/v3/reference/tickers?cursor=x&apiKey=secret',
            'https://api.massive.com/v3/reference/tickers?cursor=x&date=2020-01-01',
            'https://api.massive.com/v3/reference/tickers?cursor=x&cursor=y',
            'https://other.example/v3/reference/tickers?cursor=x'):
            with self.assertRaises(ValueError):
                m.project_body(self.request, m.legacy.render(dict(
                    m.legacy.parse_json(body([row('ACRV'), row('ACRpC')])), next_url=url)))

    def test_row_and_response_size_limits_still_apply(self):
        with self.assertRaises(ValueError):
            m.project_body(self.request, body([row('A')] * 1001))
        for raw in (b'', 'text', b' ' * (m.legacy.MAX_BODY + 1)):
            with self.assertRaises(ValueError): m.project_body(self.request, raw)

    def test_request_mutation_still_fails(self):
        for field, value in (('url', 'https://other.example'), ('trading_date', '2020-01-01'), ('page', 2)):
            with self.assertRaises(ValueError):
                m.project_body(dict(self.request, **{field: value}), body([row()]))

    def test_valid_mixed_case_across_pages(self):
        state = initialized()
        feed(state, body([row('ACRV')], 'page2'))
        feed(state, body([row('ACRpC')]))
        self.assertEqual(state.summary()[0]['accepted_rows'], 2)
        self.assertEqual(state.summary()[0]['state'], 'exhausted')

    def test_cross_page_uses_raw_last_not_canonical_maximum(self):
        state = initialized()
        feed(state, body([row('ALLZ'), row('ALLpB')], 'page2'))
        feed(state, body([row('ALLpC')]))
        self.assertEqual(state.summary()[0]['accepted_rows'], 3)

    def test_real_cross_page_regression_rejected_before_all_mutation(self):
        state = initialized()
        feed(state, body([row('ACRpC')], 'page2'))
        before = deepcopy(state.__dict__)
        with self.assertRaisesRegex(ValueError, 'cross-page ordering regression'):
            feed(state, body([row('ACRV')]))
        self.assertEqual(state.__dict__, before)

    def test_empty_intermediate_preserves_order_boundary(self):
        state = initialized()
        feed(state, body([row('ACRpC')], 'page2'))
        feed(state, body([], 'page3'))
        before = deepcopy(state.__dict__)
        with self.assertRaisesRegex(ValueError, 'cross-page ordering regression'):
            feed(state, body([row('ACRV')]))
        self.assertEqual(state.__dict__, before)

    def test_empty_terminal_after_members_is_valid_but_empty_census_is_not(self):
        state = initialized()
        with self.assertRaisesRegex(ValueError, 'empty complete census'):
            feed(state, body([]))
        feed(state, body([row('ACRpC')], 'page2'))
        feed(state, body([]))
        self.assertEqual(state.summary()[0]['state'], 'exhausted')

    def test_duplicate_canonical_identity_within_and_across_pages_rejected(self):
        for across in (False, True):
            state = initialized()
            if across: feed(state, body([row('ACRPC')], 'page2'))
            before = deepcopy(state.__dict__)
            with self.assertRaisesRegex(ValueError, 'duplicate membership identity'):
                feed(state, body([row('ACRpC')] if across else [row('ACRPC'), row('ACRpC')]))
            self.assertEqual(state.__dict__, before)

    def test_distinct_identities_and_missing_metadata_are_not_dropped(self):
        state = initialized()
        feed(state, body([row('ACRPC', composite_figi='ONE', type='OLD'),
            row('ACRpC', composite_figi='TWO')]))
        result = state.summary()[0]
        self.assertEqual(result['accepted_rows'], 2)
        self.assertEqual(result['ticker_collision_groups'], 1)
        self.assertEqual(result['missing_metadata_counts']['cik'], 2)
        self.assertEqual(result['unknown_current_type_codes'], ['', 'OLD'])

    def test_missing_forged_or_inconsistent_order_witness_rejected(self):
        for witness in (None, [], ['WRONG'], ['Z', 'A']):
            state = initialized()
            raw = body([row('A')])
            projection = dict(m.project_body(state.next_request(), raw), provider_tickers=witness)
            before = deepcopy(state.__dict__)
            with self.assertRaises(ValueError): state.accept(state.next_request(), m.sha(raw), projection)
            self.assertEqual(state.__dict__, before)

    def test_repeated_cursor_and_page_21_do_not_mutate_state(self):
        state = initialized()
        feed(state, body([row('A')], 'same'))
        before = deepcopy(state.__dict__)
        with self.assertRaisesRegex(ValueError, 'repeated cursor'):
            feed(state, body([row('B')], 'same'))
        self.assertEqual(state.__dict__, before)
        state = initialized()
        for page in range(1, 20): feed(state, body([row(f'S{page:02d}')], f'page{page + 1}'))
        before = deepcopy(state.__dict__)
        with self.assertRaisesRegex(ValueError, 'page ceiling'):
            feed(state, body([row('S20')], 'page21'))
        self.assertEqual(state.__dict__, before)

    def test_synthetic_complete_30_date_mixed_case_protocol(self):
        state, requests = m.CensusState(), []
        while (request := state.next_request()) is not None:
            requests.append(request)
            if request['kind'] == 'current_type_dictionary':
                raw = synthetic_reply(request, SECRET)['body']
            else:
                raw = body([row('ACRV' if request['page'] == 1 else 'ACRpC')],
                    'next' if request['page'] == 1 else None)
            feed(state, raw)
        self.assertEqual(len(requests), 61)
        self.assertEqual([d['date'] for d in state.summary()], list(m.legacy.DATES))
        self.assertTrue(all(d['state'] == 'exhausted' and d['accepted_rows'] == 2 for d in state.summary()))

    def test_synthetic_exact_601_attempt_maximum(self):
        state, count = m.CensusState(), 0
        while (request := state.next_request()) is not None:
            raw = (synthetic_reply(request, SECRET)['body'] if request['kind'] == 'current_type_dictionary'
                else body([row(f'S{request["page"]:02d}')], str(request['page']) if request['page'] < 20 else None))
            feed(state, raw)
            count += 1
        self.assertEqual(count, 601)
        self.assertTrue(all(d['accepted_pages'] == 20 for d in state.summary()))

    def test_wrong_request_sequence_or_body_hash_rejected(self):
        state = initialized()
        raw = body([row('A')])
        projected = m.project_body(state.next_request(), raw)
        before = deepcopy(state.__dict__)
        with self.assertRaises(ValueError):
            state.accept(m.legacy.parent.census_request(m.legacy.DATES[1]), m.sha(raw), projected)
        with self.assertRaises(ValueError): state.accept(state.next_request(), 'wrong', projected)
        self.assertEqual(state.__dict__, before)

    def test_changed_archive_pin_is_rejected(self):
        path = ROOT / m.diagnostic.BASE / 'hosted-result.zip'
        with self.assertRaisesRegex(ValueError, 'digest'):
            evidence.read_archive(path, 65103, '0' * 64)
        with self.assertRaisesRegex(ValueError, 'size'):
            evidence.read_archive(path, 65104, evidence.ARTIFACTS['hosted-result.zip'][2])

    def test_archive_symlink_is_rejected(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'link.zip'
            path.symlink_to(ROOT / m.diagnostic.BASE / 'hosted-result.zip')
            with self.assertRaisesRegex(ValueError, 'size/path'):
                evidence.read_archive(path, 65103, evidence.ARTIFACTS['hosted-result.zip'][2])

    def test_provider_free_cli_reverifies_saved_originals(self):
        result = subprocess.run([sys.executable, 'scripts/verify_census_order_repair.py'],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['rows_repaired_offline'], 1000)
        self.assertEqual(json.loads(result.stdout)['provider_requests'], 0)

    def test_no_network_is_needed_for_evidence_and_projection(self):
        with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            _, raw = evidence.verify(ROOT)
            self.assertEqual(m.project_body(self.request, raw)['raw_row_count'], 1000)


if __name__ == '__main__':
    unittest.main()
