from copy import deepcopy
import gzip
import io
from pathlib import Path
import unittest
import zipfile

import pandas as pd

from momentumbot.research import candidate_daily_source as m
from tests.test_candidate_daily_history import root, history, reply

ROOT = Path(__file__).resolve().parents[1]


def fixture(count=60):
    r = root(); state = m.capture.DailyPages(r); request = state.request()
    body = reply({'AAA': history(count)})['body']
    state.accept(request, {'status': 200, 'complete': True, 'encoding': 'identity', 'body': body})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z: z.writestr('00000.body.json', body)
    value = m.CandidateDailyArchive.__new__(m.CandidateDailyArchive)
    value.archive = zipfile.ZipFile(stream)
    value.inventory = {'00000.body.json': {'bytes': len(body), 'sha256': m.sha(body)}}
    value.contract = {'requests': [r]}
    value.locations = {r['content_sha256']: [('00000', request)]}
    value.summaries = {r['content_sha256']: state.result()}
    return value


class DailySourceTests(unittest.TestCase):
    def test_projection_preserves_short_empty_and_original_average(self):
        for count, average in ((60, 35.5), (49, None)):
            with self.subTest(count=count), fixture(count) as source:
                value = source.read_day('2026-03-09')
                self.assertEqual(value['history_by_symbol']['AAA']['average_daily_volume_50'], average)
                self.assertEqual(value['history_by_symbol']['BBB']['prior_sessions'], [])
                self.assertEqual(value['provenance']['bar_count'], count)
                self.assertFalse(value['provenance']['runtime_normalization_authorized'])
                m.capture.c.d.base.verify_seal(value['provenance'])

    def test_body_and_summary_tamper_rejected(self):
        with fixture() as source:
            source.inventory['00000.body.json']['sha256'] = '0' * 64
            with self.assertRaises(ValueError): source.read_day('2026-03-09')
        with fixture() as source:
            next(iter(source.summaries.values()))['bar_count'] += 1
            with self.assertRaises(ValueError): source.read_day('2026-03-09')

    def test_duplicate_candidate_and_unknown_date_rejected(self):
        with fixture() as source:
            with self.assertRaises(ValueError): source.read_day('2026-03-10')
            source.contract['requests'] *= 2
            with self.assertRaises(ValueError): source.read_day('2026-03-09')

    def setUp(self):
        self.frame = pd.DataFrame({'close': [2.5, 3.0]}, index=pd.to_datetime(
            ['2026-03-05T05:00:00Z', '2026-03-06T05:00:00Z']))
        self.witness = {'timestamp': '2026-03-06T05:00:00Z', 'close': 3.0,
                        'source_body_sha256': 'a' * 64}

    def compare(self, frame=None, witness=None):
        return m.compare_previous_close(self.frame if frame is None else frame,
                                        self.witness if witness is None else witness, '2026-03-09')

    def test_exact_match_not_basis_promotion(self):
        result = self.compare()
        self.assertEqual(result['status'], 'previous_close_matches')
        self.assertTrue(result['witness_is_latest_history_session'])
        self.assertFalse(result['daily_minute_share_basis_verified'])
        self.assertFalse(result['historical_scanner_enabled'])

    def test_tiny_difference_not_tolerated(self):
        self.witness['close'] = 3.000000000001
        self.assertEqual(self.compare()['history_minus_saved'], '-1/1000000000000')
        self.assertEqual(self.compare()['status'], 'previous_close_differs')

    def test_same_session_not_last_row_or_missing_fallback(self):
        self.witness.update(timestamp='2026-03-05T15:00:00Z', close=2.5)
        result = self.compare()
        self.assertEqual(result['status'], 'previous_close_matches')
        self.assertFalse(result['witness_is_latest_history_session'])
        self.witness['timestamp'] = '2026-03-04T05:00:00Z'
        self.assertEqual(self.compare()['status'], 'witness_session_unavailable')
        self.assertEqual(m.compare_previous_close(self.frame, None, '2026-03-09')['status'],
                         'saved_previous_close_unavailable')

    def test_bad_witness_rejected(self):
        for stamp in ('2026-03-06', '2026-03-09T04:00:00Z', '2026-03-10T04:00:00Z'):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                self.compare(witness={**self.witness, 'timestamp': stamp})
        for close in (True, -1, 0, float('nan'), float('inf'), '3'):
            with self.subTest(close=close), self.assertRaises(ValueError):
                self.compare(witness={**self.witness, 'close': close})

    def test_bad_history_rejected(self):
        for index in (pd.to_datetime(['2026-03-05', '2026-03-06']),
                      pd.to_datetime(['2026-03-06T05:00Z', '2026-03-05T05:00Z']),
                      pd.to_datetime(['2026-03-06T05:00Z', '2026-03-06T06:00Z']),
                      pd.to_datetime(['2026-03-06T05:00Z', '2026-03-09T04:00Z'])):
            frame = self.frame.copy(); frame.index = index
            with self.subTest(index=index), self.assertRaises(ValueError): self.compare(frame=frame)
        for close in (-1, 0, float('nan'), float('inf')):
            frame = self.frame.copy(); frame.iloc[0, 0] = close
            with self.subTest(close=close), self.assertRaises(ValueError): self.compare(frame=frame)

    def test_frozen_all_date_evidence(self):
        data = (ROOT / m.BASE / 'audit/daily-source-audit.json.gz').read_bytes()
        self.assertEqual((len(data), m.sha(data)),
                         (166974, '41be56526b97979434fdea382c365bec15845fb706ededfcf86a80336d5d88bd'))
        value = m.parse(gzip.decompress(data)); m.capture.c.d.base.verify_seal(value)
        self.assertEqual(value['content_sha256'], 'c283ae904b3d8924d818aba1da8887476db30d1f5291450993cc855698b1e0c1')
        self.assertEqual(value['counts'], {'previous_close_matches': 4018})
        self.assertEqual((len(value['days']), value['daily_bars']), (30, 318519))
        self.assertEqual((value['sufficient_history_cases'], value['available_average_volume_cases']), (3904, 3904))
        self.assertEqual(value['original_capture_pin'], m.CAPTURE_PIN)
        self.assertFalse(value['full_ranking_population_verified'])
        self.assertFalse(value['runtime_normalization_authorized'])
        for day in value['days']:
            m.capture.c.d.base.verify_seal(day['source_provenance'])
            for case in day['cases']:
                self.assertTrue(case['previous_close_comparison']['witness_is_latest_history_session'])
                self.assertEqual(case['average_volume_available'], case['sufficient_history'])


if __name__ == '__main__': unittest.main()
