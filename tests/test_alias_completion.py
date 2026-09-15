from copy import deepcopy
from datetime import datetime, date, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import pandas as pd
import yaml

from momentumbot.research import alias_completion as m
from scripts.build_causal_scanner_snapshot_v03 import _previous_split_close
from tests.test_early_pullback_census_v01 import Clock
from tests.test_identity_coverage import pair, view

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
KEYS = {'ALPACA_API_KEY': 'synthetic-key-123', 'ALPACA_API_SECRET': 'synthetic-secret-456'}
CODE = 'a' * 40


def reply(bars, token=None):
    return {'status': 200, 'complete': True, 'encoding': 'identity',
        'body': m.render({'bars': bars, 'next_page_token': token})}


def bar(day, **changes):
    row = {'t': day + 'T05:00:00Z', 'o': 2, 'h': 3, 'l': 1, 'c': 2.5, 'v': 500, 'n': 10, 'vw': 2.2}
    return {**row, **changes}


def transport(request, keys):
    return reply({s: [bar(request['trading_date'])] for s in request['params']['symbols'].split(',')})


class DailyAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.roots = m.request_plan(ROOT)

    def state(self): return m.AliasPages(self.roots[0])

    def test_fixed_union_keeps_original_31_and_four_conflict_views(self):
        self.assertEqual(len(self.roots), 17)
        self.assertEqual(sum(len(r['params']['symbols'].split(',')) for r in self.roots), 35)
        for root in self.roots:
            self.assertLess(root['params']['asof'], root['trading_date'])
            self.assertEqual(root['params']['adjustment'], 'raw')
            self.assertEqual(root['params']['timeframe'], '1Day')
            self.assertNotIn('page_token', root['params'])

    def test_target_bar_asof_and_seven_fields_preserved(self):
        state = self.state()
        request = state.request()
        state.accept(request, transport(request, KEYS))
        for value in state.result()['views']:
            self.assertEqual(value['asof'], request['params']['asof'])
            self.assertEqual(value['target_date'], request['trading_date'])
            self.assertEqual(set(value['bar']), set(m.parent.BAR_FIELDS))
            self.assertEqual(value['status'], 'captured_bar')

    def test_exhausted_empty_is_retained_and_not_retried(self):
        state = self.state()
        state.accept(state.request(), reply(None))
        self.assertTrue(all(v['status'] == 'captured_empty' and v['bar'] is None for v in state.result()['views']))
        with self.assertRaises(ValueError): state.request()

    def test_schema_order_dates_and_unknown_symbols_fail_closed(self):
        root = self.roots[0]
        symbol = root['params']['symbols'].split(',')[0]
        bad = [{symbol: [bar(root['trading_date'], n=True)]}, {'UNREQUESTED': [bar(root['trading_date'])]},
            {symbol: [bar('2030-01-01')]}, {symbol: [bar(root['trading_date']), bar(root['trading_date'])]},
            {symbol: [bar(root['trading_date'], ross_fill=5)]}]
        for bars in bad:
            state = self.state()
            with self.subTest(bars=bars), self.assertRaises(ValueError): state.accept(state.request(), reply(bars))
            with self.assertRaises(ValueError): state.request()

    def test_cursor_exhaustion_required_before_target_is_usable(self):
        state = self.state()
        request = state.request()
        response = transport(request, KEYS)
        payload = m.parse(response['body']); payload['next_page_token'] = 'next'
        response['body'] = m.render(payload)
        state.accept(request, response)
        with self.assertRaises(ValueError): state.result()
        state.accept(state.request(), reply({}))
        self.assertTrue(all(v['bar'] is not None for v in state.result()['views']))

    def test_changed_asof_and_empty_nonterminal_rejected(self):
        state = self.state(); request = state.request()
        request['params']['asof'] = request['trading_date']
        with self.assertRaises(ValueError): state.accept(request, transport(request, KEYS))
        state = self.state()
        with self.assertRaises(ValueError): state.accept(state.request(), reply({}, 'next'))


class PreviousCloseTests(unittest.TestCase):
    def test_parity_with_frozen_scanner_and_no_target_close(self):
        rows = [bar('2026-03-03', c=2), bar('2026-03-04', c=99)]
        frame = pd.DataFrame({'close': [r['c'] for r in rows]}, index=pd.to_datetime([r['t'] for r in rows]))
        expected = _previous_split_close(frame, trading_date=date(2026,3,4))
        self.assertEqual(m.previous_close(rows, '2026-03-04')['close'], expected)
        self.assertEqual(expected, 2)

    def test_missing_and_zero_last_close_do_not_fall_back(self):
        self.assertIsNone(m.previous_close([], '2026-03-04'))
        self.assertIsNone(m.previous_close([bar('2026-03-04')], '2026-03-04'))
        self.assertIsNone(m.previous_close([bar('2026-03-02'), bar('2026-03-03', c=0)], '2026-03-04'))

    def test_duplicate_naive_or_regressing_timestamps_rejected(self):
        for rows in ([bar('2026-03-03'), bar('2026-03-03')], [bar('2026-03-03'), bar('2026-03-02')],
            [bar('2026-03-03', t='2026-03-03T05:00:00')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError): m.previous_close(rows, '2026-03-04')


class JoinTests(unittest.TestCase):
    def missing(self, p):
        original = p['alias_checks'][0]['views'][2]
        return view(original['symbol'], original['asof'], original['target_date'])

    def test_only_missing_view_is_filled_without_mutating_parent(self):
        p = pair(); saved = deepcopy(p)
        out = m.complete_checks([p], [self.missing(p)])
        self.assertEqual(p, saved)
        self.assertTrue(out[0]['all_bidirectional_matches'])
        self.assertFalse(out[0]['historical_scanner_enabled'])

    def test_exact_union_no_missing_extra_or_duplicate_observations(self):
        p = pair(); v = self.missing(p)
        for values in ([], [v, v], [{**v, 'symbol': 'OTHER'}]):
            with self.subTest(values=values), self.assertRaises(ValueError): m.complete_checks([p], values)

    def test_empty_and_mismatch_remain_explicit_not_resolved(self):
        p = pair(); v = self.missing(p)
        for value in ({**v, 'status': 'captured_empty', 'bar': None}, {**v, 'bar': {**v['bar'], 'c': 2.1}}):
            with self.subTest(value=value): self.assertFalse(m.complete_checks([p], [value])[0]['all_bidirectional_matches'])


class CaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.contract = m.validate_registration(ROOT)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def runner(self, transport0=transport):
        clock = Clock()
        return m.Capture(self.contract, output=self.path/'capture', transport=transport0, keys=KEYS,
            clock_ns=clock.read, sleeper=clock.sleep, utc_now=lambda: NOW.isoformat())

    def archive(self):
        path = self.path/'capture.zip'
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted((self.path/'capture').iterdir()): z.write(p, p.name)
        return path, {'size_in_bytes':path.stat().st_size, 'digest':'sha256:'+m.sha(path.read_bytes())}

    def test_full_synthetic_capture_original_zip_replay_and_terminal_guard(self):
        runner = self.runner(); report = runner.run()
        self.assertTrue(report['protocol_complete']); self.assertEqual(report['attempt_count'],17)
        path, metadata = self.archive()
        verified = m.verify_archive(path, metadata, m.sha((self.path/'capture/inventory.json').read_bytes()), self.contract)
        self.assertEqual(len(verified['views']),35)
        self.assertEqual(verified['verified_member_count'],54)
        with self.assertRaises(ValueError): runner.run()

    def test_changed_archive_bytes_or_inventory_pin_rejected(self):
        self.runner().run(); path, metadata = self.archive()
        with self.assertRaises(ValueError): m.verify_archive(path, metadata, '0'*64, self.contract)
        path.write_bytes(path.read_bytes()+b'extra')
        with self.assertRaises(ValueError): m.verify_archive(path, metadata, '0'*64, self.contract)

    def test_unsafe_body_is_not_retained_and_no_retry_occurs(self):
        calls=[]
        def bad(request, keys):
            calls.append(request)
            return reply({'leak': keys['ALPACA_API_SECRET']})
        result = self.runner(bad).run()
        self.assertFalse(result['protocol_complete']); self.assertEqual(len(calls),1)
        self.assertEqual(result['failure'],'unsafe_or_uninspectable_body')
        self.assertFalse((self.path/'capture/00000.body.json').exists())
        self.assertTrue((self.path/'capture/inventory.json').is_file())

    def test_http_error_retained_as_failure_not_empty_observation(self):
        result = self.runner(lambda r,k:{'status':403,'body':b'{"error":"denied"}','complete':True,'encoding':'identity'}).run()
        self.assertEqual(result['attempt_count'],1); self.assertEqual(result['failure'],'http_error')
        self.assertEqual(result['results'],[])
        self.assertTrue((self.path/'capture/00000.body.json').exists())

    def test_wrong_request_and_attempt_ceiling_block_transport(self):
        runner = self.runner(lambda r,k:self.fail('transport called'))
        request = runner.state.request(); request['params']['symbols']='OTHER'
        with self.assertRaises(ValueError): runner.once(request)
        runner.attempts=m.MAX_ATTEMPTS
        with self.assertRaises(ValueError): runner.once(runner.state.request())

    def test_transport_cannot_call_massive(self):
        request=deepcopy(self.contract['requests'][0]); request['provider']='massive'
        with self.assertRaises(ValueError): m.Transport()(request,{**KEYS,'MASSIVE_API_KEY':'UNUSED_ALPACA_ONLY'})


class AuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.contract=m.validate_registration(ROOT)

    def setUp(self):
        self.env={'GITHUB_SHA':CODE,'GITHUB_RUN_ID':'12345','GITHUB_RUN_ATTEMPT':'1','GITHUB_REPOSITORY':'RoomyRems/momentumbot',
            'GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/phase-3-historical-snapshot','GITHUB_WORKFLOW_SHA':CODE,
            'GITHUB_WORKFLOW_REF':'RoomyRems/momentumbot/'+m.WORKFLOW+'@refs/heads/phase-3-historical-snapshot'}
        self.facts={'head':CODE,'parents':[m.PARENT],'parent_commit':m.PARENT,'changed_files':['A\t'+m.CONTRACT_PATH],'clean':True}

    def test_registration_and_only_alpaca_credentials(self):
        self.assertEqual(self.contract['credential_names'],list(KEYS))
        self.assertEqual(self.contract['limits']['maximum_attempts'],170)
        self.assertFalse(self.contract['strategy_or_membership_changes'])

    def test_complete_saved_source_handoff_with_synthetic_missing_views(self):
        panel=m.load_panel(ROOT)
        supplement=m.parse((ROOT/m.CONFLICT_PATH).read_bytes())
        supplied=[]
        for p in panel['continuity_pairs']+supplement['conflicts']:
            for check in p['alias_checks']:
                for missing in check['views']:
                    if missing['status'] != 'request_not_captured':continue
                    reference=next(v for v in check['views'] if v['target_date']==missing['target_date'] and v['status']!='request_not_captured')
                    supplied.append({**deepcopy(reference),'symbol':missing['symbol'],'asof':missing['asof']})
        proof=m.seal({'contract_id':m.ID,'hosted_capture_provenance_verified':True,
            'archive_verification':{'views':supplied}})
        out=m.completion(ROOT,proof)
        self.assertTrue(out['alias_mapping_checks_complete'])
        self.assertEqual(out['scanner_previous_closes'],165694)
        self.assertEqual(out['scanner_missing_previous_closes'],{})
        self.assertEqual(len(out['completed_figi_view_checks']),4)
        self.assertFalse(out['distinct_figis_merged'])
        self.assertFalse(out['membership_changed'])
        self.assertFalse(out['historical_scanner_enabled'])

    def test_expiry_wrong_parent_and_rerun_rejected(self):
        m.gate.check_launch(self.contract,self.env,self.facts,NOW)
        with self.assertRaises(ValueError): m.gate.check_launch(self.contract,{**self.env,'GITHUB_RUN_ATTEMPT':'2'},self.facts,NOW)
        with self.assertRaises(ValueError): m.gate.check_launch(self.contract,self.env,{**self.facts,'parents':['b'*40]},NOW)
        with self.assertRaises(ValueError): m.gate.check_launch(self.contract,self.env,self.facts,datetime(2026,9,22,tzinfo=timezone.utc))

    def test_bad_launch_blocks_credential_loader(self):
        with self.assertRaises(ValueError):
            m.capture(ROOT,{**self.env,'GITHUB_RUN_ATTEMPT':'2'},self.facts,NOW,self.contract['runtime'],None,None,None,
                output='unused',credential_loader=lambda:self.fail('credential read'),transport=transport,progress=lambda _:None)

    def test_old_consumption_cannot_be_reused(self):
        ref={'ref':m.REF,'object':{'type':'commit','sha':CODE}}
        m.gate.check_ref(ref,self.contract,self.env)
        with self.assertRaises(ValueError): m.gate.check_ref({**ref,'ref':m.parent.hosted.REF},self.contract,self.env)

    def test_workflow_requires_consumption_and_secrets_only_in_capture(self):
        workflow=yaml.safe_load((ROOT/m.WORKFLOW).read_text())
        self.assertEqual(set(workflow['jobs']),{'consume','capture','verify'})
        self.assertEqual(workflow['jobs']['capture']['needs'],'consume')
        self.assertEqual(workflow['jobs']['verify']['needs'],['consume','capture'])
        secrets=[name for name,spec in workflow['jobs'].items() for step in spec['steps'] if 'secrets.' in str(step)]
        self.assertEqual(secrets,['capture'])
        self.assertNotIn('MASSIVE_API_KEY',(ROOT/m.WORKFLOW).read_text())
        for spec in workflow['jobs'].values():self.assertEqual(spec['if'],'github.run_attempt == 1')


if __name__ == '__main__': unittest.main()
