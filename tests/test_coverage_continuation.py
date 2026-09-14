from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import yaml

from momentumbot.research import coverage_continuation as c
from momentumbot.research import coverage_continuation_hosted as h
from tests.test_coverage_capture import reply, split, empty, KEYS
from tests.test_early_pullback_census_v01 import Clock

ROOT = Path(__file__).resolve().parents[1]
DAY = c.old.b.DATES[0]
NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
CODE = 'a' * 40


def actions(events, token=None):
    return reply({'corporate_actions': {'name_changes': events}, 'next_page_token': token})


class OrderRepairTests(unittest.TestCase):
    def state(self, provider='alpaca'):
        return c.ActionPages(c.old.daily.identity_requests(DAY)[0 if provider == 'alpaca' else 1])

    def test_original_rejected_page_retains_all_1000_ids_and_order(self):
        raw = (ROOT / 'research/data-audits' / c.old.ID / 'rejected-corporate-actions.json').read_bytes()
        original = c.old.ActionPages(c.old.daily.identity_requests(DAY)[0])
        with self.assertRaisesRegex(ValueError, 'action date regression'):
            original.accept(original.request(), reply({}, body=raw))
        state = self.state()
        witness = state.accept(state.request(), reply({}, body=raw))
        self.assertEqual(witness['body_sha256'], '5134b32e21dc1de6f02d4872e025331440638fe2dcf150284a79ffbb8124e09a')
        self.assertEqual(len(state.rows), 1000)
        groups = c.parse(raw)['corporate_actions']
        self.assertEqual(state.rows, [{**event, 'action_type': kind} for kind, rows in sorted(groups.items()) for event in rows])
        self.assertEqual(witness['process_date_regressions']['reverse_splits'], 157)
        self.assertEqual(state.request()['page'], 2)
        with self.assertRaises(ValueError): state.result()

    def test_unsorted_and_cross_page_earlier_dates_preserved(self):
        state = self.state()
        first = [{'id': 'A', 'process_date': DAY}, {'id': 'B', 'process_date': '2026-01-05'}]
        state.accept(state.request(), actions(first, 'next'))
        state.accept(state.request(), actions([{'id': 'C', 'process_date': '2025-11-10'}]))
        result = state.result()
        self.assertEqual([r['id'] for r in result['rows']], ['A', 'B', 'C'])
        self.assertEqual([p['process_date_regressions']['name_changes'] for p in result['pages']], [1, 1])
        self.assertFalse(result['as_known_historical_feed'])

    def test_duplicates_still_fail_across_pages(self):
        state = self.state()
        event = {'id': 'A', 'process_date': DAY}
        state.accept(state.request(), actions([event], 'next'))
        with self.assertRaisesRegex(ValueError, 'duplicate action ID'): state.accept(state.request(), actions([event]))
        with self.assertRaises(ValueError): state.request()

    def test_scope_id_and_schema_guards_unchanged(self):
        for event in ({'id': '', 'process_date': DAY}, {'id': 'A', 'process_date': '2030-01-01'},
            {'id': 'A', 'process_date': '2020-01-01'}, {'id': 'A'}, {'id': 'A', 'process_date': DAY, 'action_type': 'injected'}):
            state = self.state()
            with self.assertRaises(ValueError): state.accept(state.request(), actions([event]))

    def test_changed_query_and_unsupported_group_rejected(self):
        state = self.state()
        request = state.request()
        request['params']['end'] = '2030-01-01'
        with self.assertRaises(ValueError): state.accept(request, actions([]))
        state = self.state()
        with self.assertRaises(ValueError): state.accept(state.request(), reply({'corporate_actions': {'cash_dividends': []}, 'next_page_token': None}))

    def test_cursor_cycle_empty_and_page_ceiling_unchanged(self):
        state = self.state()
        with self.assertRaises(ValueError): state.accept(state.request(), actions([], 'next'))
        state = self.state()
        for i in range(c.old.ACTION_PAGES):
            response = actions([{'id': str(i), 'process_date': DAY}], str(i))
            if i == c.old.ACTION_PAGES - 1:
                with self.assertRaises(ValueError): state.accept(state.request(), response)
            else: state.accept(state.request(), response)
        state = self.state()
        state.accept(state.request(), actions([{'id': 'A', 'process_date': DAY}], 'same'))
        with self.assertRaises(ValueError): state.accept(state.request(), actions([{'id': 'B', 'process_date': DAY}], 'same'))

    def test_massive_order_guard_not_relaxed(self):
        state = self.state('massive')
        with self.assertRaisesRegex(ValueError, 'split date/ticker regression'):
            state.accept(state.request(), reply({'status': 'OK', 'results': [split(ticker='ZZZ'), split(id='second', ticker='AAA')]}))


class PrefixAndContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = c.old.daily.load_panel(ROOT)
        cls.state = c.replay_prefix(ROOT / c.PREFIX_PATH, cls.panel, ROOT)
        cls.contract = h.validate_registration(ROOT)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def test_actual_saved_prefix_and_exact_continuation_point(self):
        state = self.state
        self.assertEqual(len(state.results), 1)
        self.assertEqual(state.results[0]['date'], DAY)
        self.assertEqual(state.request()['url'], 'https://data.alpaca.markets/v1/corporate-actions')
        self.assertEqual(state.request()['page'], 2)
        self.assertEqual(len(state.current.rows), 1000)
        self.assertEqual(c.MAX_NEW_ATTEMPTS, 14953)

    def test_tampered_prefix_rejected_before_replay(self):
        path = self.path / 'wrong.zip'
        raw = bytearray((ROOT / c.PREFIX_PATH).read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'SHA differs'): c.replay_prefix(path, self.panel, ROOT)

    def test_captured_suffix_replays_with_original_prefix_and_no_repeated_requests(self):
        # Keep the real first-day source and all three first-day tasks, then exhaust synthetically.
        # Only the task population is shortened here; the stored prefix and repair are original bytes.
        def first_day_prefix(*args):
            state = deepcopy(self.state)
            state.tasks = state.tasks[:3]
            return state
        clock, requests = Clock(), []
        def transport(request, keys):
            requests.append(deepcopy(request))
            return empty(request, keys)
        with patch.object(c, 'replay_prefix', side_effect=first_day_prefix):
            runner = c.Capture(self.contract, self.panel, prefix_path=ROOT / c.PREFIX_PATH, root=ROOT,
                output=self.path / 'capture', keys=KEYS, transport=transport,
                clock_ns=clock.read, sleeper=clock.sleep, utc_now=lambda: NOW.isoformat())
            result = runner.run()
            self.assertTrue(result['protocol_complete'])
            self.assertEqual(result['new_attempt_count'], 2)
            self.assertEqual(result['total_attempt_count'], 49)
            self.assertEqual(requests[0], self.state.request())
            self.assertFalse(any(r['url'].endswith('/bars') for r in requests))
            archive = self.path / 'capture.zip'
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as handle:
                for member in runner.store.path.iterdir(): handle.writestr(member.name, member.read_bytes())
            result = c.verify_archive(archive, expected_bytes=archive.stat().st_size, expected_sha256=c.sha(archive.read_bytes()),
                expected_inventory_sha256=c.sha((runner.store.path / 'inventory.json').read_bytes()),
                contract=self.contract, panel=self.panel, root=ROOT, prefix_output=self.path / 'reused.zip')
            self.assertEqual(result['new_attempt_count'], 2)
            self.assertEqual(result['verified_member_count'], 10)
            self.assertFalse(result['historical_replay_enabled'])

    def test_remaining_ceiling_and_failure_retention(self):
        clock = Clock()
        with patch.object(c, 'replay_prefix', return_value=deepcopy(self.state)):
            runner = c.Capture(self.contract, self.panel, prefix_path=ROOT / c.PREFIX_PATH, root=ROOT,
                output=self.path / 'capture', keys=KEYS, transport=lambda *_: self.fail('transport called'),
                clock_ns=clock.read, sleeper=clock.sleep)
        with patch.object(c, 'MAX_NEW_ATTEMPTS', 0), self.assertRaises(ValueError): runner.run()
        saved = c.parse((runner.store.path / 'report.json').read_bytes())
        self.assertEqual(saved['new_attempt_count'], 0)
        self.assertEqual(saved['reused_attempt_count'], 47)
        self.assertFalse(saved['protocol_complete'])
        self.assertTrue((runner.store.path / 'prefix.zip').is_file())


class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.contract = h.validate_registration(ROOT)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.env = {'GITHUB_SHA': CODE, 'GITHUB_RUN_ID': '12345', 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_REPOSITORY': 'RoomyRems/momentumbot', 'GITHUB_EVENT_NAME': 'push',
            'GITHUB_REF': 'refs/heads/phase-3-historical-snapshot', 'GITHUB_WORKFLOW_SHA': CODE,
            'GITHUB_WORKFLOW_REF': 'RoomyRems/momentumbot/' + h.WORKFLOW + '@refs/heads/phase-3-historical-snapshot'}
        self.facts = {'head': CODE, 'parents': [h.PARENT], 'parent_commit': h.PARENT, 'changed_files': ['A\t' + h.CONTRACT_PATH], 'clean': True}

    def test_launch_scope_and_expiry(self):
        h.gate.check_launch(self.contract, self.env, self.facts, NOW)
        for key, value in (('GITHUB_SHA', 'b'*40), ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
            ('GITHUB_WORKFLOW_REF', 'other'), ('GITHUB_REF', 'refs/heads/main')):
            with self.assertRaises(ValueError): h.gate.check_launch(self.contract, dict(self.env, **{key:value}), self.facts, NOW)
        with self.assertRaises(ValueError): h.gate.check_launch(self.contract, self.env, dict(self.facts, clean=False), NOW)
        with self.assertRaises(ValueError): h.gate.check_launch(self.contract, self.env, self.facts, datetime(2026,9,21,tzinfo=timezone.utc))

    def test_old_consumption_never_reused(self):
        ref = {'ref': h.REF, 'object': {'type': 'commit', 'sha': CODE}}
        h.gate.check_ref(ref, self.contract, self.env)
        with self.assertRaises(ValueError): h.gate.check_ref(dict(ref, ref=c.parent.REF), self.contract, self.env)

    def test_preflight_roundtrip_and_tamper(self):
        ci={'id':456,'head_sha':CODE,'path':'.github/workflows/ci.yml','event':'push','status':'completed','conclusion':'success',
            'run_attempt':1,'head_branch':'phase-3-historical-snapshot','repository':{'full_name':'RoomyRems/momentumbot'}}
        jobs={'total_count':1,'jobs':[{'run_id':456,'head_sha':CODE,'name':'test','status':'completed','conclusion':'success',
            'steps':[{'name':n,'status':'completed','conclusion':'success'} for n in ('Install package','Run tests','Compile')]}]}
        ref={'ref':h.REF,'object':{'type':'commit','sha':CODE}}
        for name,value in (('ci.json',ci),('ci-jobs.json',jobs),('consumed-ref.json',ref)):
            (self.path/name).write_bytes(c.render(value))
        self.env['PREFLIGHT_SHA256']=h.gate.prepare(self.path,self.contract,self.env,self.contract['runtime'])
        self.env['PREFLIGHT_ARTIFACT_ID']='789'
        files=h.gate.d.read_files(self.path,h.gate.d.PREFLIGHT_FILES)
        artifact={'id':789,'name':f'{h.ID}-consumption-12345-1','expired':False,'size_in_bytes':10000,'digest':'sha256:'+'a'*64,
            'workflow_run':{'id':12345,'head_sha':CODE,'head_branch':'phase-3-historical-snapshot'}}
        h.gate.verify_preflight(files,self.contract,self.env,self.contract['runtime'],ref,artifact)
        files['launch.json']+=b' '
        with self.assertRaises(ValueError): h.gate.verify_preflight(files,self.contract,self.env,self.contract['runtime'],ref,artifact)
        jobs['jobs'][0]['steps'][1]['conclusion']='skipped'
        with self.assertRaises(ValueError): h.gate.d.check_ci(ci,jobs,self.env)

    def test_bad_launch_blocks_key_loader(self):
        with self.assertRaises(ValueError):
            h.capture(ROOT,dict(self.env,GITHUB_RUN_ATTEMPT='2'),self.facts,NOW,self.contract['runtime'],None,None,None,None,None,
                output=self.path/'capture',credential_loader=lambda:self.fail('key read'),transport=empty,progress=lambda _:None)

    def test_workflow_scopes_secrets_and_reuses_setup(self):
        workflow=yaml.safe_load((ROOT/h.WORKFLOW).read_text())
        self.assertEqual(set(workflow['jobs']),{'consume','capture','verify'})
        self.assertEqual(workflow['jobs']['capture']['needs'],'consume')
        self.assertEqual(workflow['jobs']['verify']['needs'],['consume','capture'])
        secrets=[job for job,spec in workflow['jobs'].items() for step in spec['steps'] if 'secrets.' in str(step)]
        self.assertEqual(secrets,['capture'])
        for spec in workflow['jobs'].values():
            self.assertEqual(spec['if'],'github.run_attempt == 1')
            self.assertTrue(any(s.get('uses')=='./.github/actions/source-runtime' for s in spec['steps']))


if __name__ == '__main__': unittest.main()
