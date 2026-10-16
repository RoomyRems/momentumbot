from pathlib import Path
import io
import math
import tempfile
import unittest
import zipfile

import pandas as pd

from momentumbot.research import candidate_rvol_exact_source as m
from tests.test_candidate_rvol_coarse import plan
from tests.test_scanner_minutes import bar, reply

ROOT = Path(__file__).resolve().parents[1]


def frame(day, values=(10,), offsets=(0,)):
    start = pd.Timestamp(day).tz_localize(m.capture.daily.ET) + pd.Timedelta(hours=4)
    return pd.DataFrame({'volume': list(values)},
                        index=pd.to_datetime([start + pd.Timedelta(minutes=i) for i in offsets], utc=True))


def case():
    target = '2026-03-09'
    history = {d.date().isoformat(): frame(d.date().isoformat())
               for d in pd.bdate_range(end='2026-03-06', periods=50)}
    current = frame(target, (50, 10), (0, 1))
    coarse = {d: f.copy() for d, f in history.items()}
    coarse[target] = frame(target, (60,))
    return dict(target=target, raw=current.copy(), saved_split=current, history=history, coarse_history=coarse)


class ExactSourceTests(unittest.TestCase):
    def test_exact_rvol_is_causal_aligned_and_dst_safe(self):
        args = case()
        curve, audit = m.integrate_case(**args)
        self.assertEqual(curve.tolist(), [5, 6])
        self.assertTrue(curve.index.equals(args['raw'].index))
        self.assertEqual(curve.index[0].isoformat(), '2026-03-09T08:00:00+00:00')
        self.assertTrue(audit['exact_same_time_rvol_complete'])
        args['saved_split'].iloc[1, 0] = 1000
        args['coarse_history'][args['target']].iloc[0, 0] = 1050
        changed, _ = m.integrate_case(**args)
        self.assertEqual(changed.iloc[0], curve.iloc[0])

    def test_refresh_replaces_only_volume_and_preserves_original(self):
        args = case()
        original = args['saved_split'].copy()
        args['saved_split'] = original * 25
        args['refresh'] = original
        before = args['saved_split'].copy()
        curve, audit = m.integrate_case(**args)
        self.assertEqual(curve.tolist(), [5, 6])
        self.assertTrue(audit['refresh_resolves_original_difference'])
        pd.testing.assert_frame_equal(args['saved_split'], before)
        self.assertFalse(audit['daily_minute_share_basis_verified'])

    def test_any_target_or_history_volume_difference_withholds_curve(self):
        for location in ['target', 'history']:
            with self.subTest(location=location):
                args = case()
                day = args['target'] if location == 'target' else min(args['history'])
                args['coarse_history'][day].iloc[0, 0] += 1
                curve, audit = m.integrate_case(**args)
                self.assertIsNone(curve)
                self.assertFalse(audit['exact_same_time_rvol_complete'])
                self.assertEqual(audit['status'], 'source_disagreement')

    def test_refresh_and_raw_timestamp_mismatch_withholds_curve(self):
        args = case()
        args['refresh'] = frame(args['target'], (60,), (0,))
        curve, audit = m.integrate_case(**args)
        self.assertIsNone(curve)
        self.assertFalse(audit['raw_split_refresh_timestamps_match'])

    def test_missing_future_and_wrong_coarse_sessions_are_rejected(self):
        for kind in ['missing', 'future', 'coarse']:
            with self.subTest(kind=kind):
                args = case()
                if kind == 'missing': args['history'].pop(min(args['history']))
                elif kind == 'future': args['history'][args['target']] = args['history'].pop(min(args['history']))
                else: args['coarse_history'].pop(min(args['history']))
                with self.assertRaises(ValueError): m.integrate_case(**args)

    def test_zero_volume_exhausted_sessions_and_undefined_values_survive(self):
        args = case()
        for day in args['history']:
            args['history'][day] = frame(day, (), ())
            args['coarse_history'][day] = frame(day, (), ())
        curve, audit = m.integrate_case(**args)
        self.assertTrue(all(math.isinf(v) for v in curve))
        self.assertEqual(audit['empty_prior_sessions'], 50)
        self.assertEqual(m.encode_curve(curve)[0][1], 'positive_infinity')
        args['saved_split']['volume'] = 0
        args['coarse_history'][args['target']]['volume'] = 0
        curve, _ = m.integrate_case(**args)
        self.assertTrue(curve.isna().all())
        self.assertIsNone(m.encode_curve(curve)[0][1])

    def test_no_uncaptured_ten_oclock_value_and_bad_volume_rejected(self):
        args = case()
        tail = frame(args['target'], (1000000,), (360,))
        args['raw'] = pd.concat([args['raw'], tail])
        args['saved_split'] = pd.concat([args['saved_split'], tail])
        curve, _ = m.integrate_case(**args)
        self.assertEqual(len(curve), 2)
        for bad in [-1, float('nan'), float('inf'), True]:
            args = case()
            args['saved_split'] = args['saved_split'].astype(object)
            args['saved_split'].iloc[0, 0] = bad
            with self.assertRaises(ValueError): m.integrate_case(**args)

    def test_history_outside_window_duplicate_or_off_grid_rejected(self):
        for kind in ['outside', 'duplicate', 'off_grid']:
            args = case(); day = min(args['history']); f = args['history'][day]
            if kind == 'outside': f.index += pd.Timedelta(hours=6)
            elif kind == 'duplicate': args['history'][day] = pd.concat([f, f])
            else: f.index += pd.Timedelta(seconds=1)
            with self.assertRaises(ValueError): m.integrate_case(**args)

    def test_pinned_original_proof_rejects_tamper(self):
        proof = m.accepted_proof(ROOT)
        self.assertEqual(proof['archive_verification']['bar_count'], 3309900)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / m.BASE / 'original-verification.zip'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'forged verification')
            with self.assertRaises(ValueError): m.accepted_proof(td)

    def fixture(self):
        days = [{'trading_date': '2026-03-09', 'cases': [{'symbol': 'AAA', 'mismatched_buckets': 1,
                 'prior_sessions': sorted(r['observation_date'] for r in plan()['requests'][:-1]),
                 'acquisition_filter': {'retain_for_exact': True}}]}]
        roots = m.capture.source.exact_requests(plan()['requests'], days)
        roots += m.capture.target_rechecks(plan()['requests'], days)
        source = m.CandidateExactArchive.__new__(m.CandidateExactArchive)
        source.contract = {'requests': roots}; source.selection = {'days': days}
        source.locations = {}; source.summaries = {}; source.inventory = {}
        blob = io.BytesIO()
        with zipfile.ZipFile(blob, 'w') as z:
            for i, root in enumerate(roots):
                parser = m.capture.ExactPages(root); request = parser.request()
                response = reply({'AAA': [bar(root['params']['start'])]}) if i in (0, 50) else reply({})
                parser.accept(request, response); key = root['content_sha256']; member = f'{i:05d}'
                source.locations[key] = [(member, request)]; source.summaries[key] = parser.result()
                name = member + '.body.json'; body = response['body']; z.writestr(name, body)
                source.inventory[name] = {'bytes': len(body), 'sha256': m.sha(body)}
        source.archive = zipfile.ZipFile(io.BytesIO(blob.getvalue())); self.addCleanup(source.close)
        return source

    def test_archive_reader_keeps_empty_sessions_and_separates_target_refresh(self):
        result = self.fixture().read_day('2026-03-09')
        history = result['sessions_by_symbol']['AAA']
        self.assertEqual(len(history), 50)
        self.assertEqual(sum(f.empty for f in history.values()), 49)
        self.assertEqual(len(result['target_refresh_by_symbol']['AAA']), 1)
        self.assertFalse(result['provenance']['historical_scanner_enabled'])

    def test_archive_reader_rejects_missing_refresh_history_or_tampered_page(self):
        for kind in ['refresh', 'history', 'body', 'duplicate']:
            with self.subTest(kind=kind):
                source = self.fixture()
                if kind == 'refresh': source.contract['requests'].pop()
                elif kind == 'history': source.contract['requests'].pop(0)
                elif kind == 'duplicate': source.contract['requests'].append(source.contract['requests'][0])
                else: source.inventory['00000.body.json']['sha256'] = '0' * 64
                with self.assertRaises(ValueError): source.read_day('2026-03-09')


if __name__ == '__main__':
    unittest.main()
