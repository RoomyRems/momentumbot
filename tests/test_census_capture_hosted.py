from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml
import zipfile

from momentumbot.research import census_capture_hosted as m
from tests.test_census_capture import mixed_reply
from tests.test_early_pullback_census_v01 import Clock, SECRET, STAMP

ROOT = Path(__file__).resolve().parents[1]
CODE = 'a' * 40
NOW = datetime(2026, 9, 12, 22, tzinfo=timezone.utc)


class HostedCensusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.contract = m.validate_registration(ROOT)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {'GITHUB_SHA': CODE, 'GITHUB_RUN_ID': '12345', 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_REPOSITORY': 'RoomyRems/momentumbot', 'GITHUB_EVENT_NAME': 'push',
            'GITHUB_REF': 'refs/heads/phase-3-historical-snapshot', 'GITHUB_WORKFLOW_SHA': CODE,
            'GITHUB_WORKFLOW_REF': 'RoomyRems/momentumbot/' + m.WORKFLOW + '@refs/heads/phase-3-historical-snapshot'}
        self.facts = {'head': CODE, 'parents': [m.PARENT], 'parent_commit': m.PARENT,
            'changed_files': ['A\t' + m.CONTRACT_PATH], 'clean': True}
        self.ci = {'id': 456, 'head_sha': CODE, 'path': '.github/workflows/ci.yml', 'event': 'push',
            'status': 'completed', 'conclusion': 'success', 'run_attempt': 1,
            'head_branch': 'phase-3-historical-snapshot', 'repository': {'full_name': 'RoomyRems/momentumbot'}}
        self.ci_jobs = {'total_count': 1, 'jobs': [{'run_id': 456, 'head_sha': CODE, 'name': 'test',
            'status': 'completed', 'conclusion': 'success', 'steps': [{'name': n, 'status': 'completed', 'conclusion': 'success'}
                for n in ('Install package', 'Run tests', 'Compile')]}]}
        self.ref = {'ref': m.REF, 'object': {'type': 'commit', 'sha': CODE}}
        self.artifact = self.metadata('consumption', 789, 10000, 'd' * 64)
        self.calls = []

    def metadata(self, role, identity, size, digest):
        return {'id': identity, 'name': f'{m.ID}-{role}-12345-1', 'expired': False,
            'size_in_bytes': size, 'digest': 'sha256:' + digest,
            'workflow_run': {'id': 12345, 'head_sha': CODE, 'head_branch': 'phase-3-historical-snapshot'}}

    def prepare(self):
        path = self.root / 'preflight'
        path.mkdir()
        for name, doc in (('ci.json', self.ci), ('ci-jobs.json', self.ci_jobs), ('consumed-ref.json', self.ref)):
            m.d.base.write_once(path / name, doc)
        self.env['CENSUS_PREFLIGHT_SHA256'] = m.prepare(path, self.contract, self.env, m.RUNTIME)
        self.env['CENSUS_PREFLIGHT_ARTIFACT_ID'] = '789'
        return m.d.read_files(path, m.d.PREFLIGHT_FILES)

    def capture(self, *, files=None, loader=lambda: SECRET, **changes):
        files = self.prepare() if files is None else files
        clock = Clock()
        def transport(request, credential):
            self.calls.append(request)
            return mixed_reply(request, credential)
        def session(contract, **kwargs):
            return m.capture_engine.CaptureSession(contract, **kwargs, clock_ns=clock.read,
                sleeper=clock.sleep, utc_now=lambda: STAMP)
        args = dict(root=ROOT, output=self.root / 'capture', launch_output=self.root / 'launch',
            preflight=files, env=self.env, facts=self.facts, now=NOW, runtime=m.RUNTIME,
            live_ref=self.ref, artifact=self.artifact, credential_loader=loader,
            transport=transport, session_factory=session)
        args.update(changes)
        return m.capture(**args)

    def bundle(self):
        self.capture()
        metadata = {}
        for role, identity in (('launch', 790), ('capture', 791)):
            path = self.root / (role + '.zip')
            with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
                for file in sorted((self.root / role).iterdir()): archive.writestr(file.name, file.read_bytes())
            metadata[role] = self.metadata(role, identity, path.stat().st_size, m.sha(path.read_bytes()))
        self.env.update(CENSUS_LAUNCH_ARTIFACT_ID='790', CENSUS_CAPTURE_ARTIFACT_ID='791',
            CENSUS_CAPTURE_INVENTORY_SHA256=m.sha((self.root / 'capture/inventory.json').read_bytes()))
        jobs = {'total_count': 3, 'jobs': [{'name': name, 'run_id': 12345, 'head_sha': CODE,
            'status': 'in_progress' if name == 'verify' else 'completed',
            'conclusion': None if name == 'verify' else 'success',
            'steps': [{'name': 'Run', 'status': 'completed', 'conclusion': 'success'}]} for name in ('consume', 'capture', 'verify')]}
        return dict(root=ROOT, env=self.env, facts=self.facts, now=NOW, runtime=m.RUNTIME,
            live_ref=self.ref, preflight_artifact=self.artifact, launch_artifact=metadata['launch'],
            capture_artifact=metadata['capture'], jobs=jobs, launch_zip=self.root / 'launch.zip', capture_zip=self.root / 'capture.zip')

    def test_registration_fixes_scope_and_preserves_uncertain_entitlement(self):
        self.assertEqual(self.contract['selected_dates'], list(m.legacy.DATES))
        self.assertEqual(self.contract['limits']['maximum_http_attempts'], 601)
        self.assertTrue(self.contract['automatic_archive_verification'])
        self.assertFalse(self.contract['authorization']['account_entitlement_verified'])
        self.assertFalse(self.contract['authorization']['subscription_changes_authorized'])
        self.assertEqual(self.contract['authorization']['latest_user_message'], 'You may continue')
        self.assertFalse(self.contract['historical_replay_enabled'])

    def test_successful_credential_gated_capture_and_independent_hosted_replay(self):
        args = self.bundle()
        calls = len(self.calls)
        result = m.verify_hosted(**args)
        self.assertEqual(result['archive_verification']['attempt_count'], 61)
        self.assertEqual(result['archive_verification']['verified_member_count'], 247)
        self.assertEqual(result['provider_requests_during_verification'], 0)
        self.assertEqual(len(self.calls), calls)
        self.assertFalse(result['historical_replay_enabled'])

    def test_changed_preflight_fails_before_key_or_transport(self):
        files = self.prepare()
        files['launch.json'] += b' '
        with self.assertRaises(ValueError): self.capture(files=files, loader=lambda: self.fail('key accessed'))
        self.assertEqual(self.calls, [])

    def test_missing_extra_preflight_and_reuse_fail(self):
        files = self.prepare()
        for altered in ({n: b for n, b in files.items() if n != 'launch.json'}, dict(files, extra=b'{}')):
            with self.assertRaises(ValueError): self.capture(files=altered, loader=lambda: self.fail('key accessed'))
        with self.assertRaises(ValueError): m.prepare(self.root / 'preflight', self.contract, self.env, m.RUNTIME)

    def test_wrong_ref_or_artifact_fails_before_key(self):
        files = self.prepare()
        for change in ({'live_ref': dict(self.ref, ref=m.d.REF)},
            {'artifact': dict(self.artifact, id=790)}, {'artifact': dict(self.artifact, expired=True)},
            {'artifact': dict(self.artifact, digest='bad')}, {'runtime': dict(m.RUNTIME, python='other')}):
            with self.assertRaises(ValueError): self.capture(files=files, loader=lambda: self.fail('key accessed'), **change)

    def test_wrong_head_branch_event_attempt_or_workflow_fails(self):
        for key, value in (('GITHUB_SHA', 'b' * 40), ('GITHUB_REF', 'refs/heads/main'),
            ('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('GITHUB_RUN_ATTEMPT', '2'),
            ('GITHUB_WORKFLOW_SHA', 'b' * 40), ('GITHUB_WORKFLOW_REF', 'other'), ('GITHUB_REPOSITORY', 'other')):
            with self.assertRaises(ValueError): m.check_launch(self.contract, dict(self.env, **{key: value}), self.facts, NOW)

    def test_parent_dirty_merge_or_missing_new_contract_fails(self):
        for change in ({'clean': False}, {'parent_commit': CODE}, {'parents': [m.PARENT, CODE]}, {'changed_files': []}):
            with self.assertRaises(ValueError): m.check_launch(self.contract, self.env, dict(self.facts, **change), NOW)

    def test_authorization_is_time_bounded(self):
        for day in (11, 19):
            with self.assertRaises(ValueError):
                m.check_launch(self.contract, self.env, self.facts, datetime(2026, 9, day, tzinfo=timezone.utc))

    def test_ci_wrong_code_failed_or_skipped_test_prevents_preparation(self):
        for change in ({'head_sha': 'b' * 40}, {'conclusion': 'failure'}, {'run_attempt': 2}):
            with self.assertRaises(ValueError): m.d.check_ci(dict(self.ci, **change), self.ci_jobs, self.env)
        jobs = deepcopy(self.ci_jobs)
        jobs['jobs'][0]['steps'][1]['conclusion'] = 'skipped'
        with self.assertRaises(ValueError): m.d.check_ci(self.ci, jobs, self.env)

    def test_existing_output_or_launch_blocks_second_credential_read(self):
        files = self.prepare()
        (self.root / 'capture').mkdir()
        with self.assertRaises(ValueError): self.capture(files=files, loader=lambda: self.fail('key accessed'))
        (self.root / 'capture').rmdir()
        self.capture(files=files)
        with self.assertRaises(ValueError): self.capture(files=files, loader=lambda: self.fail('key accessed'))

    def test_missing_key_preserves_launch_failure_and_zero_provider_calls(self):
        with self.assertRaises(ValueError): self.capture(loader=lambda: '')
        self.assertEqual(self.calls, [])
        link = m.d.base.frozen(self.root / 'launch/capture-link.json')
        self.assertEqual(link['failure'], 'launch_or_capture_error')
        self.assertIsNone(link['capture_files']['inventory.json'])

    def test_bad_inventory_output_pin_cannot_pass_hosted_verification(self):
        args = self.bundle()
        args['env'] = dict(self.env, CENSUS_CAPTURE_INVENTORY_SHA256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'inventory hash'): m.verify_hosted(**args)

    def test_wrong_artifact_code_run_role_id_or_digest_cannot_pass(self):
        args = self.bundle()
        for change in ({'id': 999}, {'name': 'wrong'}, {'workflow_run': {'id': 2}}, {'digest': 'sha256:' + '0' * 64}):
            with self.assertRaises(ValueError): m.verify_hosted(**dict(args, capture_artifact=dict(args['capture_artifact'], **change)))

    def test_failed_skipped_or_wrong_capture_job_cannot_pass(self):
        args = self.bundle()
        for field, value in (('conclusion', 'failure'), ('head_sha', 'b' * 40), ('run_id', 9)):
            jobs = deepcopy(args['jobs'])
            jobs['jobs'][1][field] = value
            with self.assertRaises(ValueError): m.verify_hosted(**dict(args, jobs=jobs))
        jobs = deepcopy(args['jobs'])
        jobs['jobs'][1]['steps'][0]['conclusion'] = 'skipped'
        with self.assertRaises(ValueError): m.verify_hosted(**dict(args, jobs=jobs))

    def test_workflow_only_capture_step_has_provider_key(self):
        workflow = yaml.safe_load((ROOT / m.WORKFLOW).read_text())
        found = []
        for job_name, job in workflow['jobs'].items():
            for step in job['steps']:
                if 'secrets.' in json.dumps(step): found.append((job_name, step.get('id')))
        self.assertEqual(found, [('capture', 'capture')])
        self.assertEqual(workflow['jobs']['capture']['needs'], 'consume')
        self.assertEqual(workflow['jobs']['verify']['needs'], ['consume', 'capture'])
        self.assertEqual(workflow['jobs']['capture']['permissions']['contents'], 'read')
        self.assertEqual(workflow['jobs']['verify']['permissions']['contents'], 'read')
        for job in workflow['jobs'].values(): self.assertEqual(job['if'], 'github.run_attempt == 1')

    def test_workflow_ci_precedes_consumption_and_verifier_uses_original_zips(self):
        workflow = yaml.safe_load((ROOT / m.WORKFLOW).read_text())
        consume = workflow['jobs']['consume']['steps']
        commands = '\n'.join(s.get('run', '') for s in consume)
        self.assertLess(commands.index('gh run watch'), commands.index('--method POST'))
        self.assertIn('--commit "$GITHUB_SHA"', commands)
        verify = '\n'.join(s.get('run', '') for s in workflow['jobs']['verify']['steps'])
        self.assertIn('$CENSUS_CAPTURE_ARTIFACT_ID/zip', verify)
        self.assertIn('python scripts/run_census_capture.py verify', verify)
        self.assertNotIn('secrets.', verify)

    def test_offline_cli_validates_without_credential_discovery(self):
        result = subprocess.run([sys.executable, 'scripts/run_census_capture.py', 'validate'],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['provider_requests'], 0)


if __name__ == '__main__': unittest.main()
