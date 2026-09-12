from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

from momentumbot.research import census_payload_diagnostic as m
from tests.test_early_pullback_census_v01 import body, row, synthetic_reply, SECRET

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 12, 20, tzinfo=timezone.utc)
CODE = 'a' * 40


class PayloadDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = m.validate_registration(ROOT)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {'GITHUB_SHA': CODE, 'GITHUB_RUN_ID': '12345', 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_REPOSITORY': 'RoomyRems/momentumbot', 'GITHUB_EVENT_NAME': 'push',
            'GITHUB_REF': 'refs/heads/phase-3-historical-snapshot', 'GITHUB_WORKFLOW_SHA': CODE,
            'GITHUB_WORKFLOW_REF': 'RoomyRems/momentumbot/' + m.WORKFLOW_PATH + '@refs/heads/phase-3-historical-snapshot'}
        self.facts = {'head': CODE, 'parents': [m.PARENT], 'parent_commit': m.PARENT,
            'changed_files': ['A\t' + m.CONTRACT_PATH], 'clean': True}
        self.ci = {'id': 456, 'head_sha': CODE, 'path': '.github/workflows/ci.yml', 'event': 'push',
            'status': 'completed', 'conclusion': 'success', 'run_attempt': 1,
            'head_branch': 'phase-3-historical-snapshot', 'repository': {'full_name': 'RoomyRems/momentumbot'}}
        self.jobs = {'total_count': 1, 'jobs': [{'run_id': 456, 'head_sha': CODE, 'name': 'test',
            'status': 'completed', 'conclusion': 'success', 'steps': [{'name': name, 'status': 'completed',
                'conclusion': 'success'} for name in ('Install package', 'Run tests', 'Compile')]}]}
        self.ref = {'ref': m.REF, 'object': {'type': 'commit', 'sha': CODE}}
        self.artifact = {'id': 789, 'name': m.ID + '-consumption-12345-1', 'expired': False,
            'size_in_bytes': 10000, 'digest': 'sha256:' + 'd' * 64,
            'workflow_run': {'id': 12345, 'head_sha': CODE, 'head_branch': 'phase-3-historical-snapshot'}}

    def prepare(self):
        path = self.root / 'preflight'
        path.mkdir()
        for name, value in (('ci.json', self.ci), ('ci-jobs.json', self.jobs), ('consumed-ref.json', self.ref)):
            m.base.write_once(path / name, value)
        self.env['DIAGNOSTIC_PREFLIGHT_SHA256'] = m.prepare(path, self.contract, self.env, m.previous.RUNTIME)
        self.env['DIAGNOSTIC_PREFLIGHT_ARTIFACT_ID'] = '789'
        return m.read_files(path, m.PREFLIGHT_FILES)

    def capture(self, reply=None, key=SECRET, loader=None, transport=None, files=None):
        files = self.prepare() if files is None else files
        self.calls = []
        def default_transport(request, credential):
            self.calls.append(request)
            self.assertTrue((self.root / 'output' / 'intent.json').is_file())
            return reply or synthetic_reply(request, credential)
        with patch.object(m, 'validate_registration', return_value=self.contract):
            result = m.capture(root=self.root, output=self.root / 'output', preflight=files,
                env=self.env, facts=self.facts, now=NOW, runtime=m.previous.RUNTIME,
                live_ref=self.ref, artifact=self.artifact, credential_loader=loader or (lambda: key),
                transport=transport or default_transport)
        saved = {p.name: p.read_bytes() for p in (self.root / 'output').iterdir()}
        inventory = m.base.json_object(saved.pop('inventory.json'))
        self.assertEqual(inventory, m.inventory(saved))
        self.assertFalse(any(SECRET.encode() in raw for raw in saved.values()))
        return result

    def test_exact_frozen_parent_request_and_no_runtime_authority(self):
        self.assertEqual(self.contract['requests'], [m.adapter.parent.census_request('2026-03-04')])
        self.assertEqual(self.contract['maximum_requests'], 1)
        self.assertFalse(self.contract['pagination'])
        self.assertFalse(self.contract['historical_replay_enabled'])
        self.assertEqual(self.contract['parent_registration_sha256'], m.PARENT_REGISTRATION)

    def test_exact_same_commit_launch_allows_batched_code_commit(self):
        facts = dict(self.facts, changed_files=[*self.facts['changed_files'], 'A\tsrc/new.py'])
        m.check_launch(self.contract, self.env, facts, NOW)

    def test_rerun_dispatch_wrong_sha_branch_workflow_or_repo_rejected(self):
        for key, value in (('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
            ('GITHUB_SHA', 'b' * 40), ('GITHUB_REF', 'refs/heads/main'),
            ('GITHUB_WORKFLOW_SHA', 'b' * 40), ('GITHUB_WORKFLOW_REF', 'wrong'), ('GITHUB_REPOSITORY', 'wrong')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.check_launch(self.contract, dict(self.env, **{key: value}), self.facts, NOW)

    def test_dirty_merge_wrong_parent_or_missing_authorization_rejected(self):
        for changes in ({'clean': False}, {'parents': [m.PARENT, CODE]}, {'parent_commit': CODE}, {'changed_files': []}):
            with self.assertRaises(ValueError):
                m.check_launch(self.contract, self.env, dict(self.facts, **changes), NOW)

    def test_expired_and_future_authorization_rejected(self):
        for day in (11, 20):
            with self.assertRaises(ValueError):
                m.check_launch(self.contract, self.env, self.facts, datetime(2026, 9, day, tzinfo=timezone.utc))

    def test_ci_must_match_code_and_succeed_in_every_step(self):
        m.check_ci(self.ci, self.jobs, self.env)
        for changes in ({'head_sha': 'b' * 40}, {'conclusion': 'failure'}, {'run_attempt': 2}, {'head_branch': 'main'}):
            with self.assertRaises(ValueError): m.check_ci(dict(self.ci, **changes), self.jobs, self.env)
        jobs = deepcopy(self.jobs)
        jobs['jobs'][0]['steps'][1]['conclusion'] = 'skipped'
        with self.assertRaises(ValueError): m.check_ci(self.ci, jobs, self.env)

    def test_preflight_roundtrip_and_immutability(self):
        files = self.prepare()
        m.verify_preflight(files, self.contract, self.env, m.previous.RUNTIME, self.ref, self.artifact)
        with self.assertRaises(ValueError): m.prepare(self.root / 'preflight', self.contract, self.env, m.previous.RUNTIME)

    def test_bad_preflight_never_reads_key(self):
        files = self.prepare()
        files['launch.json'] += b' '
        with self.assertRaises(ValueError): self.capture(files=files, loader=lambda: self.fail('key read'))

    def test_bad_ref_artifact_or_runtime_never_passes(self):
        files = self.prepare()
        for artifact in (dict(self.artifact, id=790), dict(self.artifact, expired=True), dict(self.artifact, digest='invalid')):
            with self.assertRaises(ValueError):
                m.verify_preflight(files, self.contract, self.env, m.previous.RUNTIME, self.ref, artifact)
        with self.assertRaises(ValueError):
            m.verify_preflight(files, self.contract, self.env, dict(m.previous.RUNTIME, pandas='3'), self.ref, self.artifact)
        with self.assertRaises(ValueError):
            m.verify_preflight(files, self.contract, self.env, m.previous.RUNTIME, dict(self.ref, ref='old-consumed'), self.artifact)

    def test_symlink_or_extra_preflight_rejected(self):
        self.prepare()
        (self.root / 'link').symlink_to(self.root / 'preflight', target_is_directory=True)
        with self.assertRaises(ValueError): m.read_files(self.root / 'link', m.PREFLIGHT_FILES)
        (self.root / 'preflight' / 'extra').touch()
        with self.assertRaises(ValueError): m.read_files(self.root / 'preflight', m.PREFLIGHT_FILES)

    def test_valid_page_retained_once_without_pagination(self):
        reply = dict(synthetic_reply(m.request(), SECRET), body=body([row()], cursor='unused-cursor'))
        result = self.capture(reply=reply)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['attempts'], 1)
        self.assertTrue(result['body_retained'])
        self.assertTrue(result['diagnosis']['legacy_accepted'])
        self.assertFalse(result['historical_replay_enabled'])

    def test_rejected_order_body_is_retained_and_identified(self):
        raw = body([row('Z'), row('A')])
        result = self.capture(reply=dict(synthetic_reply(m.request(), SECRET), body=raw))
        self.assertIsNone(result['failure'])
        self.assertEqual(result['diagnosis']['reason'], 'provider page order regressed')
        self.assertEqual((self.root / 'output' / 'response.body.json').read_bytes(), raw)
        self.assertEqual(result['body_sha256'], m.sha(raw))

    def test_unknown_field_bad_filter_and_bad_cursor_keep_specific_reason(self):
        cases = [(body([row(new_field='x')]), 'unknown ticker metadata field'),
                 (body([dict(row(), active=False)]), 'membership filter mismatch'),
                 (body([row()], cursor='ok').replace(b'api.massive.com', b'api.other.com'), 'pagination origin or path differs')]
        for raw, reason in cases:
            self.assertEqual(m.diagnose(raw)['reason'], reason)

    def test_duplicate_key_body_is_safely_inspectable_but_legacy_rejected(self):
        raw = b'{"status":"OK","status":"ERROR","results":[]}'
        self.assertEqual(m.safe_to_retain(raw, SECRET), (True, None))
        self.assertEqual(m.diagnose(raw)['reason'], 'duplicate JSON key')

    def test_raw_percent_encoded_and_unicode_escaped_secrets_are_not_retained(self):
        escaped = ''.join('\\u%04x' % ord(c) for c in SECRET)
        for value in (SECRET, escaped):
            raw = ('{"unexpected":"' + value + '"}').encode()
            self.assertEqual(m.safe_to_retain(raw, SECRET), (False, 'credential_echo'))
        key = 'key+percent%only'
        self.assertEqual(m.safe_to_retain(json.dumps({'x': 'key%2Bpercent%25only'}).encode(), key), (False, 'credential_echo'))

    def test_duplicate_key_overwrite_cannot_hide_escaped_credential(self):
        escaped = ''.join('\\u%04x' % ord(c) for c in SECRET)
        raw = ('{"same":"' + escaped + '","same":"clean"}').encode()
        self.assertEqual(m.safe_to_retain(raw, SECRET), (False, 'credential_echo'))

    def test_secret_echo_capture_keeps_only_hash(self):
        result = self.capture(reply=dict(synthetic_reply(m.request(), SECRET), body=json.dumps({'extra': SECRET}).encode()))
        self.assertEqual(result['failure'], 'credential_echo')
        self.assertFalse(result['body_retained'])
        self.assertFalse((self.root / 'output' / 'response.body.json').exists())

    def test_uninspectable_json_not_retained(self):
        self.assertEqual(m.safe_to_retain(b'{bad-json', SECRET), (False, 'uninspectable_json'))

    def test_unexpected_exception_text_is_never_disclosed(self):
        with patch.object(m.adapter, 'project_body', side_effect=RuntimeError(SECRET)):
            self.assertEqual(m.diagnose(body([row()]))['reason'], 'unclassified_validation_error')

    def test_provider_denial_does_not_retry(self):
        result = self.capture(reply=dict(synthetic_reply(m.request(), SECRET), status=403))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['failure'], 'http_error')
        self.assertFalse(result['body_retained'])

    def test_transport_exception_does_not_retry_or_leak(self):
        calls = []
        def transport(*args):
            calls.append(1)
            raise RuntimeError(SECRET)
        result = self.capture(transport=transport)
        self.assertEqual(calls, [1])
        self.assertEqual(result['failure'], 'launch_or_transport_error')

    def test_missing_credential_records_zero_attempts(self):
        result = self.capture(key='')
        self.assertEqual(result['attempts'], 0)
        self.assertEqual(self.calls, [])

    def test_output_reuse_blocks_second_key_read(self):
        files = self.prepare()
        self.capture(files=files)
        with self.assertRaises(FileExistsError): self.capture(files=files, loader=lambda: self.fail('key reread'))

    def test_incomplete_oversize_or_encoded_body_not_retained(self):
        for key, value, reason in [('complete', False, 'incomplete_body'), ('encoding', 'gzip', 'content_encoding'),
            ('body', b'x' * (m.adapter.MAX_BODY + 1), 'response_too_large')]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                previous_root = self.root
                self.root = Path(directory)
                result = self.capture(reply=dict(synthetic_reply(m.request(), SECRET), **{key: value}))
                self.root = previous_root
                self.assertEqual(result['failure'], reason)
                self.assertFalse(result['body_retained'])

    def test_workflow_waits_same_commit_ci_then_consumes_before_secrets(self):
        flow = yaml.safe_load((ROOT / m.WORKFLOW_PATH).read_text())
        self.assertEqual(flow.get('on', flow.get(True)), {'push': {'branches': ['phase-3-historical-snapshot'], 'paths': [m.CONTRACT_PATH]}})
        self.assertFalse(flow['concurrency']['cancel-in-progress'])
        consume, diagnose = flow['jobs']['consume'], flow['jobs']['diagnose']
        self.assertEqual(diagnose['needs'], 'consume')
        self.assertNotIn('secrets.', json.dumps(consume))
        steps = consume['steps']
        wait = next(i for i,s in enumerate(steps) if 'gh run watch' in s.get('run', ''))
        create = next(i for i,s in enumerate(steps) if '--method POST' in s.get('run', ''))
        retain = next(i for i,s in enumerate(steps) if s.get('id') == 'preserve')
        self.assertLess(wait, create)
        self.assertLess(create, retain)
        self.assertIn('--commit "$GITHUB_SHA"', steps[wait]['run'])
        for job in flow['jobs'].values():
            self.assertEqual(job['if'], 'github.run_attempt == 1')
            for step in job['steps']:
                if 'uses' in step: self.assertRegex(step['uses'], r'@[0-9a-f]{40}$')
        secret_steps = [s for s in diagnose['steps'] if 'secrets.' in json.dumps(s)]
        self.assertEqual(len(secret_steps), 1)
        self.assertEqual(set(secret_steps[0]['env']), {'MASSIVE_API_KEY'})


if __name__ == '__main__':
    unittest.main()
