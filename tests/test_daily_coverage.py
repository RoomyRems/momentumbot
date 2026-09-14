from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import unittest

from momentumbot.research import daily_coverage as m
from tests.test_census_scanner_bridge import row

DAY = m.bridge.DATES[0]


def bar(day=DAY, **changes):
    value = {'t': day + 'T05:00:00Z', 'o': 2, 'h': 3, 'l': 1, 'c': 2,
        'v': 100, 'n': 5, 'vw': 2}
    value.update(changes)
    return value


def response(bars=None, token=None, **changes):
    value = {'status': 200, 'body': m.bridge.render({'bars': bars, 'next_page_token': token}),
        'complete': True, 'encoding': 'identity'}
    value.update(changes)
    return value


class DailyCoverageTests(unittest.TestCase):
    def setUp(self):
        self.projected = m.bridge.project_date([row('AAA'), row('BBB', composite_figi='FIGI2')], DAY)
        self.root = m.bridge.coverage_requests(self.projected)[0]

    def pages(self):
        return m.DailyPages(self.projected, self.root)

    def reject(self, payload):
        pages = self.pages()
        request = pages.request()
        with self.assertRaises(ValueError): pages.accept(request, payload)
        with self.assertRaises(ValueError): pages.request()
        with self.assertRaises(ValueError): pages.result()

    def test_full_paginated_date_handoff(self):
        state = m.DailyCoverage(self.projected)
        prior = (date.fromisoformat(DAY) - timedelta(days=1)).isoformat()
        for adjustment in ('raw', 'split'):
            request = state.request()
            self.assertEqual(request['params']['adjustment'], adjustment)
            state.accept(request, response({'AAA': [bar(prior), bar()]}, 'next'))
            request = state.request()
            self.assertEqual(request['params']['page_token'], 'next')
            state.accept(request, response({'BBB': [bar(prior), bar()]}))
        result = state.result()
        self.assertTrue(all(r['coverage_pass'] for r in result['coverage']['records'].values()))
        out = m.bridge.bind_coverage([row('AAA'), row('BBB', composite_figi='FIGI2')], DAY,
            result['coverage'], expected_coverage_sha256=result['coverage_sha256'])
        self.assertEqual(out['membership_symbols'], ['AAA', 'BBB'])
        self.assertFalse(out['historical_scanner_enabled'])
        self.assertFalse(result['provider_origin_authenticated'])

    def test_missing_symbols_only_after_exhaustion(self):
        pages = self.pages()
        pages.accept(pages.request(), response({'AAA': [bar()]}, 'next'))
        with self.assertRaises(ValueError): pages.result()
        pages.accept(pages.request(), response({}))
        self.assertFalse(pages.result()['observations']['BBB']['target_session_present'])

    def test_incomplete_date_has_no_coverage(self):
        state = m.DailyCoverage(self.projected)
        state.accept(state.request(), response({}))
        with self.assertRaises(ValueError): state.result()

    def test_empty_exhausted_both_adjustments_is_failed_coverage_not_invalid(self):
        state = m.DailyCoverage(self.projected)
        for _ in range(2): state.accept(state.request(), response())
        for record in state.result()['coverage']['records'].values():
            self.assertFalse(record['invalid_symbol'])
            self.assertFalse(record['coverage_pass'])

    def test_http_failures_do_not_infer_invalid_symbols_or_retry(self):
        for status in (400, 401, 403, 429, 500, True):
            with self.subTest(status=status): self.reject(response(status=status))

    def test_partial_or_compressed_response_fails(self):
        for changes in ({'complete': False}, {'complete': 1}, {'encoding': 'gzip'}):
            with self.subTest(changes=changes): self.reject(response(**changes))

    def test_unexpected_symbols_fail(self):
        self.reject(response({'OTHER': [bar()]}))

    def test_root_scope_cannot_change(self):
        for field, value in [('asof', '2026-09-14'), ('feed', 'iex'), ('adjustment', 'all')]:
            root = deepcopy(self.root)
            root['params'][field] = value
            root = m.seal({k: v for k, v in root.items() if k != 'content_sha256'})
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.DailyPages(self.projected, root)

    def test_request_mutation_does_not_change_internal_root(self):
        pages = self.pages()
        request = pages.request()
        request['params']['symbols'] = 'OTHER'
        self.assertEqual(pages.request()['params']['symbols'], 'AAA,BBB')
        with self.assertRaises(ValueError): pages.accept(request, response({}))

    def test_page_token_is_exact_and_not_a_new_query(self):
        pages = self.pages()
        pages.accept(pages.request(), response({'AAA': [bar()]}, 'opaque+/='))
        request = pages.request()
        self.assertEqual(request['params']['page_token'], 'opaque+/=')
        self.assertEqual({k: v for k, v in request['params'].items() if k != 'page_token'}, self.root['params'])

    def test_repeated_cursor_fails_closed(self):
        pages = self.pages()
        pages.accept(pages.request(), response({'AAA': [bar()]}, 'same'))
        with self.assertRaises(ValueError):
            pages.accept(pages.request(), response({'BBB': [bar()]}, 'same'))
        with self.assertRaises(ValueError): pages.result()

    def test_empty_nonterminal_page_fails(self):
        self.reject(response({}, 'next'))

    def test_bad_tokens_fail(self):
        for token in ('', 'has space', '\n', 'x' * 4097, 1, False):
            with self.subTest(token=str(token)[:20]): self.reject(response({'AAA': [bar()]}, token))

    def test_duplicate_and_regressing_bars_fail(self):
        prior = (date.fromisoformat(DAY) - timedelta(days=1)).isoformat()
        for bars in ([bar(), bar()], [bar(), bar(prior)]):
            self.reject(response({'AAA': bars}))

    def test_cross_page_symbol_regression_fails(self):
        pages = self.pages()
        pages.accept(pages.request(), response({'BBB': [bar()]}, 'next'))
        with self.assertRaises(ValueError): pages.accept(pages.request(), response({'AAA': [bar()]}))

    def test_object_key_order_not_semantic(self):
        pages = self.pages()
        pages.accept(pages.request(), response({'BBB': [bar()], 'AAA': [bar()]}))
        self.assertTrue(pages.result()['observations']['AAA']['target_session_present'])

    def test_future_old_and_naive_stamps_fail(self):
        for stamp in ('2030-01-01T05:00:00Z', '2020-01-01T05:00:00Z', DAY + 'T05:00:00', DAY):
            self.reject(response({'AAA': [bar(t=stamp)]}))

    def test_new_york_session_date_not_utc_date(self):
        pages = self.pages()
        pages.accept(pages.request(), response({'AAA': [bar(t=DAY + 'T00:00:00Z')]}))
        observations = pages.result()['observations']['AAA']
        self.assertTrue(observations['prior_session_present'])
        self.assertFalse(observations['target_session_present'])

    def test_extra_fields_and_bad_numeric_types_fail(self):
        for changes in ({'ross_fill': 2}, {'c': True}, {'v': -1}, {'n': 1.2}, {'h': 1}, {'vw': None}):
            with self.subTest(changes=changes): self.reject(response({'AAA': [bar(**changes)]}))

    def test_duplicate_json_keys_fail(self):
        self.reject(response(body=b'{"bars":{},"bars":{},"next_page_token":null}'))

    def test_nonfinite_numbers_fail(self):
        for value in (b'NaN', b'Infinity', b'1e9999'):
            raw = m.bridge.render({'bars': {'AAA': [bar()]}, 'next_page_token': None})
            self.reject(response(body=raw.replace(b'"vw":2', b'"vw":' + value)))

    def test_raw_split_disagreement_is_not_passing_coverage(self):
        state = m.DailyCoverage(self.projected)
        prior = (date.fromisoformat(DAY) - timedelta(days=1)).isoformat()
        state.accept(state.request(), response({'AAA': [bar(prior), bar()]}))
        state.accept(state.request(), response({'AAA': [bar(prior)]}))
        record = state.result()['coverage']['records']['AAA']
        self.assertTrue(record['raw_target_session_present'])
        self.assertFalse(record['split_target_session_present'])
        self.assertFalse(record['coverage_pass'])

    def test_duplicate_local_session_with_distinct_timestamps_fails(self):
        self.reject(response({'AAA': [bar(), bar(t=DAY + 'T06:00:00Z')]}))

    def test_terminal_request_cannot_be_repeated(self):
        pages = self.pages()
        pages.accept(pages.request(), response({}))
        with self.assertRaises(ValueError): pages.request()
        self.assertEqual(len(pages.result()['pages']), 1)

    def test_body_bound_and_exact_envelope(self):
        self.reject(response(body=b' ' * (m.MAX_BODY + 1)))
        self.reject(response(body=b'{"bars":{},"next_page_token":null,"future_label":1}'))

    def test_pagination_ceiling_is_fail_closed(self):
        # Ten distinct days fit the fixed 14-day window; a next cursor on page 10 is rejected.
        pages = self.pages()
        for i in range(m.MAX_PAGES):
            day = (date.fromisoformat(DAY) - timedelta(days=12 - i)).isoformat()
            if i == m.MAX_PAGES - 1:
                with self.assertRaises(ValueError):
                    pages.accept(pages.request(), response({'AAA': [bar(day)]}, str(i)))
            else:
                pages.accept(pages.request(), response({'AAA': [bar(day)]}, str(i)))
        with self.assertRaises(ValueError): pages.result()

    def test_failed_date_cannot_restart(self):
        state = m.DailyCoverage(self.projected)
        with self.assertRaises(ValueError): state.accept(state.request(), response(status=403))
        with self.assertRaises(ValueError): state.request()
        with self.assertRaises(ValueError): state.result()

    def test_identity_scope_is_exact_120_days(self):
        for day in m.bridge.DATES:
            alpaca, massive = m.identity_requests(day)
            start = (date.fromisoformat(day) - timedelta(days=120)).isoformat()
            self.assertEqual(alpaca['params']['start'], start)
            self.assertEqual(massive['params']['execution_date.gte'], start)
            self.assertEqual(alpaca['params']['end'], day)
            self.assertEqual(massive['params']['execution_date.lte'], day)
            self.assertEqual(alpaca['params']['data_quality'], 'complete')
        with self.assertRaises(ValueError): m.identity_requests('2030-01-01')

    def test_published_panel_and_initial_request_population(self):
        panel = m.load_panel(Path(__file__).resolve().parents[1])
        self.assertEqual(panel['initial_request_count'], 1380)
        self.assertEqual(sum(len(m.identity_requests(d['trading_date'])) for d in panel['days']), 60)
        self.assertFalse(panel['capture_authorized'])


if __name__ == '__main__': unittest.main()
