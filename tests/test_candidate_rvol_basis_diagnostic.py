from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest

from momentumbot.research import candidate_rvol_basis_diagnostic as m
from tests.test_candidate_rvol_coarse import plan
from tests.test_scanner_minutes import bar, reply

ROOT = Path(__file__).resolve().parents[1]


def histories():
    coarse = plan()['requests']
    selection = [{'trading_date': '2026-03-09', 'cases': [{'symbol': 'AAA',
                  'mismatched_buckets': 0, 'acquisition_filter': {'retain_for_exact': True}}]}]
    exact = m.parent.capture.source.exact_requests(coarse, selection)
    pair = []
    for roots in (exact, coarse[:-1]):
        pair.append({r['observation_date']: {'root': r, 'pages': [],
                                            'rows': [bar(r['params']['start'])]} for r in roots})
    return pair


class BasisDiagnosticTests(unittest.TestCase):
    def test_rollup_ohlc_volume_and_trade_count_use_exact_decimal_sums(self):
        minute = [bar('2026-03-09T08:00:00Z', v=0.1),
                  bar('2026-03-09T08:14:00Z', c=2, v=0.2)]
        coarse = [bar('2026-03-09T08:00:00Z', c=2, v=0.3, n=6)]
        result = m.compare_history_buckets(minute, coarse, '2026-03-09')
        self.assertEqual(result['differences'], [])
        self.assertFalse(result['basis_correction_proven'])

    def test_price_and_volume_discrepancies_are_described_not_rescaled(self):
        one = [bar('2026-03-09T08:00:00Z', o=1, h=1.5, l=.5, c=1.25, v=200)]
        fifteen = [bar('2026-03-09T08:00:00Z')]
        before = deepcopy(one)
        result = m.compare_history_buckets(one, fifteen, '2026-03-09')
        self.assertEqual(result['price_differing_buckets'], 1)
        self.assertEqual(result['volume_differing_buckets'], 1)
        self.assertEqual(result['trade_count_differing_buckets'], 0)
        self.assertEqual(result['differences'][0]['minute_rollup']['c'], '5/4')
        self.assertEqual(one, before)
        self.assertFalse(result['basis_correction_proven'])

    def test_missing_bars_are_not_silently_called_matching_prices(self):
        result = m.compare_history_buckets([], [bar('2026-03-09T08:00:00Z', v=0, n=0)], '2026-03-09')
        self.assertEqual(result['volume_differing_buckets'], 0)
        self.assertEqual(result['presence_differing_buckets'], 1)
        self.assertEqual(result['price_differing_buckets'], 1)
        self.assertIsNone(result['differences'][0]['minute_rollup'])
        empty = m.compare_history_buckets([], [], '2026-03-09')
        self.assertTrue(empty['both_sources_empty'])
        self.assertFalse(empty['basis_correction_proven'])

    def test_invalid_values_fail_without_assert_statements(self):
        for changes in [{'v': True}, {'v': -1}, {'h': float('inf')}, {'c': float('nan')},
                        {'n': 1.5}, {'l': 4}, {'o': 0}, {'v': '100'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                m.compare_history_buckets([bar('2026-03-09T08:00:00Z', **changes)], [], '2026-03-09')

    def test_time_window_grid_order_and_dst_are_enforced(self):
        valid = bar('2026-03-06T09:00:00Z')
        self.assertEqual(m.compare_history_buckets([valid], [valid], '2026-03-06')['differences'], [])
        for stamp in ['2026-03-09T08:00:00', '2026-03-08T08:00:00Z',
                      '2026-03-09T07:59:00Z', '2026-03-09T14:00:00Z',
                      '2026-03-09T08:00:01Z', '2026-03-09T08:00:00.000000001Z']:
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                m.compare_history_buckets([bar(stamp)], [], '2026-03-09')
        for rows in [[bar('2026-03-09T08:00:00Z')] * 2,
                     [bar('2026-03-09T08:01:00Z'), bar('2026-03-09T08:00:00Z')]]:
            with self.assertRaises(ValueError): m.compare_history_buckets(rows, [], '2026-03-09')
        with self.assertRaises(ValueError):
            m.compare_history_buckets([], [bar('2026-03-09T08:01:00Z')], '2026-03-09')

    def test_request_compatibility_is_not_adjustment_vintage_proof(self):
        a, b = histories(); day = min(a)
        result = m.compatible_requests(a[day]['root'], b[day]['root'], 'AAA')
        self.assertTrue(result['compatible_requests'])
        self.assertFalse(result['asof_establishes_adjustment_cutoff'])
        self.assertFalse(result['adjustment_vintage_verified'])
        for key, value in [('feed', 'iex'), ('adjustment', 'raw'), ('asof', '2026-03-10'),
                           ('end', a[day]['root']['params']['end']), ('symbols', 'BBB')]:
            bad = deepcopy(b[day]['root']); bad['params'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.compatible_requests(a[day]['root'], bad, 'AAA')
        bad = deepcopy(b[day]['root']); bad['membership_sha256'] = 'different'
        with self.assertRaises(ValueError): m.compatible_requests(a[day]['root'], bad, 'AAA')

    def test_all_fifty_sessions_and_parent_discrepancy_reproduction_required(self):
        a, b = histories()
        case = {'trading_date': '2026-03-09', 'symbol': 'AAA', 'parent_day_sha256': 'parent',
                'target_comparison': {}, 'prior_session_differences': []}
        result = m.diagnose_case(case, a, b)
        self.assertEqual(result['prior_session_count'], 50)
        self.assertEqual(result['status'], 'withheld_unresolved_basis')
        self.assertFalse(result['exact_same_time_rvol_complete'])
        self.assertFalse(result['correction_authorized'])
        self.assertFalse(result['historical_scanner_enabled'])
        wrong = deepcopy(b); wrong.pop(min(wrong))
        with self.assertRaises(ValueError): m.diagnose_case(case, a, wrong)
        wrong = deepcopy(b); wrong[min(wrong)]['rows'][0]['v'] += 1
        with self.assertRaisesRegex(ValueError, 'parent volume disagreements'):
            m.diagnose_case(case, a, wrong)
        wrong = deepcopy(a); wrong[min(wrong)]['root']['observation_date'] = '2026-01-01'
        with self.assertRaisesRegex(ValueError, 'root observation'):
            m.diagnose_case(case, wrong, b)

    def fixture_archive(self):
        a, _ = histories()
        source = SimpleNamespace(contract={'requests': [v['root'] for v in a.values()]},
                                 locations={}, summaries={})
        blobs = {}
        for ordinal, entry in enumerate(a.values()):
            root = entry['root']; parser = m.parent.capture.ExactPages(root)
            request = parser.request(); response = reply({'AAA': entry['rows']} if ordinal == 0 else {})
            parser.accept(request, response)
            member = f'{ordinal:05d}'; key = root['content_sha256']
            source.locations[key] = [(member, request)]; source.summaries[key] = parser.result()
            blobs[member + '.body.json'] = response['body']
            blobs[member + '.intent.json'] = m.parent.capture.render({'request': request, 'started_at': 'saved-start'})
            blobs[member + '.receipt.json'] = m.parent.capture.render(
                {'body_sha256': m.sha(response['body']), 'finished_at': 'saved-end'})
        source._read = blobs.__getitem__
        return source, blobs

    def test_history_reader_preserves_empty_sessions_and_page_provenance(self):
        source, _ = self.fixture_archive()
        result = m.read_symbol_history(source, '2026-03-09', 'AAA')
        self.assertEqual(len(result), 50)
        self.assertEqual(sum(not v['rows'] for v in result.values()), 49)
        self.assertEqual(result[min(result)]['pages'][0]['started_at'], 'saved-start')

    def test_history_reader_rejects_summary_receipt_page_and_population_tamper(self):
        for kind in ('summary', 'receipt', 'body', 'missing', 'duplicate'):
            source, blobs = self.fixture_archive()
            if kind == 'summary': source.summaries[next(iter(source.summaries))]['bar_count'] += 1
            elif kind == 'receipt':
                blobs['00000.receipt.json'] = m.parent.capture.render({'body_sha256': 'wrong', 'finished_at': 'end'})
            elif kind == 'body': blobs['00000.body.json'] = reply({})['body']
            elif kind == 'missing': source.contract['requests'].pop()
            else: source.contract['requests'].append(source.contract['requests'][0])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                m.read_symbol_history(source, '2026-03-09', 'AAA')

    def test_selection_comes_from_immutable_parent_not_manual_ticker_list(self):
        result = m.withheld_cases(ROOT)
        self.assertEqual([(c['trading_date'], c['symbol']) for c in result],
                         [('2026-03-25', 'MGN'), ('2026-05-19', 'RUBI')])


if __name__ == '__main__':
    unittest.main()
