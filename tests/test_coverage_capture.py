from copy import deepcopy
from datetime import datetime, timezone
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import yaml

from momentumbot.research import coverage_capture as c
from momentumbot.research import coverage_capture_hosted as h
from tests.test_census_scanner_bridge import row
from tests.test_early_pullback_census_v01 import Clock

ROOT = Path(__file__).resolve().parents[1]
DAY = c.b.DATES[0]
KEYS = {name: 'synthetic-secret-' + name for name in c.KEYS}
CODE = 'a' * 40
NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


def panel():
    return {'days': [c.b.project_date([row('SYNTHETIC')], day) for day in c.b.DATES]}


def reply(payload, **changes):
    return dict({'status': 200, 'body': c.render(payload), 'complete': True, 'encoding': 'identity'}, **changes)


def empty(request, keys):
    if request['url'].endswith('/bars'): return reply({'bars': {}, 'next_page_token': None})
    if request['provider'] == 'alpaca': return reply({'corporate_actions': {}, 'next_page_token': None})
    return reply({'results': [], 'status': 'OK'})


def split(**changes):
    return dict({'id': 'split1', 'ticker': 'SYNTHETIC', 'execution_date': DAY,
        'split_from': 1, 'split_to': 2, 'adjustment_type': 'forward_split'}, **changes)


class ActionTests(unittest.TestCase):
    def state(self, provider='alpaca'):
        return c.ActionPages(c.daily.identity_requests(DAY)[0 if provider == 'alpaca' else 1])

    def test_alpaca_two_pages_preserve_optional_future_payment_without_claiming_availability(self):
        state = self.state()
        state.accept(state.request(), reply({'corporate_actions': {'name_changes': [
            {'id': 'one', 'process_date': DAY, 'old_symbol': 'OLD', 'new_symbol': 'NEW'}]}, 'next_page_token': 'next'}))
        with self.assertRaises(ValueError): state.result()
        self.assertEqual(state.request()['params']['page_token'], 'next')
        state.accept(state.request(), reply({'corporate_actions': {'forward_splits': [
            {'id': 'two', 'process_date': DAY, 'payable_date': '2030-01-01'}]}, 'next_page_token': None}))
        self.assertEqual(len(state.result()['rows']), 2)
        self.assertFalse(state.result()['as_known_historical_feed'])

    def test_massive_cursor_is_same_origin_path_and_original_parameters(self):
        state = self.state('massive')
        state.accept(state.request(), reply({'status': 'OK', 'results': [split()],
            'next_url': 'https://api.massive.com/stocks/v1/splits?cursor=next'}))
        self.assertEqual(state.request()['params'], {'cursor': 'next'})
        state.accept(state.request(), reply({'status': 'OK', 'results': [split(id='split2', ticker='ZZZ')]}))
        self.assertEqual(len(state.result()['rows']), 2)

    def test_massive_bad_continuations_fail(self):
        for url in ('http://api.massive.com/stocks/v1/splits?cursor=x',
            'https://evil.example/stocks/v1/splits?cursor=x', 'https://api.massive.com/orders?cursor=x',
            'https://api.massive.com/stocks/v1/splits?apiKey=secret&cursor=x',
            'https://api.massive.com/stocks/v1/splits?cursor=x&cursor=y',
            'https://api.massive.com/stocks/v1/splits?cursor=x&limit=1'):
            with self.subTest(url=url):
                state = self.state('massive')
                with self.assertRaises(ValueError): state.accept(state.request(), reply({'status': 'OK', 'results': [split()], 'next_url': url}))
                with self.assertRaises(ValueError): state.request()

    def test_duplicate_action_id_cannot_cross_pages(self):
        state = self.state()
        event = {'id': 'one', 'process_date': DAY}
        state.accept(state.request(), reply({'corporate_actions': {'name_changes': [event]}, 'next_page_token': 'next'}))
        with self.assertRaises(ValueError): state.accept(state.request(), reply({'corporate_actions': {'name_changes': [event]}, 'next_page_token': None}))

    def test_action_dates_and_groups_fail_closed(self):
        for kind, event in (('cash_dividends', {'id': 'one', 'process_date': DAY}),
            ('name_changes', {'id': 'one'}), ('name_changes', {'id': 'one', 'process_date': '2030-01-01'}),
            ('name_changes', {'id': 'one', 'process_date': '2020-01-01'})):
            state = self.state()
            with self.assertRaises(ValueError): state.accept(state.request(), reply({'corporate_actions': {kind: [event]}, 'next_page_token': None}))

    def test_split_invalid_ratio_scope_schema(self):
        for changes in ({'split_from': 0}, {'split_to': True}, {'execution_date': '2030-01-01'},
            {'ticker': ''}, {'adjustment_type': 'other'}, {'future_label': 1}):
            state = self.state('massive')
            with self.assertRaises(ValueError): state.accept(state.request(), reply({'status': 'OK', 'results': [split(**changes)]}))

    def test_empty_nonterminal_and_repeated_cursors_rejected(self):
        state = self.state()
        with self.assertRaises(ValueError): state.accept(state.request(), reply({'corporate_actions': {}, 'next_page_token': 'next'}))
        state = self.state('massive')
        url = 'https://api.massive.com/stocks/v1/splits?cursor=x'
        state.accept(state.request(), reply({'status': 'OK', 'results': [split()], 'next_url': url}))
        with self.assertRaises(ValueError): state.accept(state.request(), reply({'status': 'OK', 'results': [split(id='second')], 'next_url': url}))

    def test_action_page_limit(self):
        state = self.state()
        for i in range(c.ACTION_PAGES):
            value = reply({'corporate_actions': {'name_changes': [{'id': str(i), 'process_date': DAY}]}, 'next_page_token': str(i)})
            if i == c.ACTION_PAGES - 1:
                with self.assertRaises(ValueError): state.accept(state.request(), value)
            else: state.accept(state.request(), value)
        with self.assertRaises(ValueError): state.result()


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.panel = panel()
        self.contract = c.seal({'contract_id': c.ID})

    def runner(self, transport=empty, suffix='capture'):
        clock = Clock()
        return c.Capture(self.contract, self.panel, output=self.path / suffix, transport=transport,
            keys=KEYS, clock_ns=clock.read, sleeper=clock.sleep, utc_now=lambda: NOW.isoformat())

    def bundle(self, files):
        path = self.path / 'capture.zip'
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, raw in files.items(): archive.writestr(name, raw)
        return dict(path=path, expected_bytes=path.stat().st_size, expected_sha256=c.sha(path.read_bytes()),
            expected_inventory_sha256=c.sha(files['inventory.json']), contract=self.contract, panel=self.panel)

    def test_complete_30_date_capture_replays_original_bytes(self):
        runner = self.runner()
        result = runner.run()
        self.assertTrue(result['protocol_complete'])
        self.assertEqual(result['attempt_count'], 120)
        files = {p.name: p.read_bytes() for p in runner.store.path.iterdir()}
        verified = c.verify_archive(**self.bundle(files))
        self.assertEqual(verified['completed_tasks'], 90)
        self.assertEqual(verified['verified_member_count'], 363)
        self.assertFalse(verified['historical_replay_enabled'])

    def test_intent_exists_before_transport_and_secrets_absent(self):
        calls = []
        def transport(request, keys):
            self.assertTrue((self.path / 'capture' / f'{len(calls):05d}.intent.json').exists())
            calls.append(request)
            return empty(request, keys)
        runner = self.runner(transport)
        runner.run()
        self.assertEqual(len(calls), 120)
        for path in runner.store.path.iterdir():
            self.assertFalse(any(k.encode() in path.read_bytes() for k in KEYS.values()))

    def test_safe_bad_response_retained_without_retry(self):
        raw = c.render({'unexpected': 'schema'})
        runner = self.runner(lambda *_: reply({}, body=raw))
        result = runner.run()
        self.assertEqual(result['attempt_count'], 1)
        self.assertEqual(result['failure'], 'invalid_payload_or_chain')
        self.assertEqual((runner.store.path / '00000.body.json').read_bytes(), raw)
        with self.assertRaises(ValueError): runner.run()

    def test_all_three_credentials_and_duplicate_key_echo_are_blocked(self):
        for i, secret in enumerate(KEYS.values()):
            escaped = ''.join('\\u%04x' % ord(char) for char in secret)
            raw = ('{"echo":"' + escaped + '","echo":"safe"}').encode()
            runner = self.runner(lambda *_: reply({}, body=raw), str(i))
            result = runner.run()
            self.assertEqual(result['failure'], 'unsafe_or_uninspectable_body')
            self.assertFalse((runner.store.path / '00000.body.json').exists())

    def test_http_error_and_partial_json_are_retained(self):
        for i, changes in enumerate(({'status': 403}, {'complete': False})):
            runner = self.runner(lambda *_, changes=changes: reply({'message': 'safe provider error'}, **changes), str(i))
            result = runner.run()
            self.assertFalse(result['protocol_complete'])
            self.assertTrue((runner.store.path / '00000.body.json').exists())

    def test_non_json_compressed_oversized_and_transport_exception_have_safe_receipts(self):
        def raises(*_): raise OSError(KEYS['ALPACA_API_KEY'])
        transports = [lambda *_: reply({}, body=b'not-json'), lambda *_: reply({}, encoding='gzip'),
            lambda *_: reply({}, body=b' ' * (c.daily.MAX_BODY + 1)), raises]
        for i, transport in enumerate(transports):
            runner = self.runner(transport, str(i))
            result = runner.run()
            self.assertEqual(result['attempt_count'], 1)
            self.assertFalse(result['protocol_complete'])
            self.assertTrue((runner.store.path / 'inventory.json').exists())
            self.assertFalse((runner.store.path / '00000.body.json').exists())

    def test_tampered_report_fails_even_after_repinning_inventory_and_zip(self):
        runner = self.runner()
        runner.run()
        files = {p.name: p.read_bytes() for p in runner.store.path.iterdir()}
        report = c.parse(files['report.json'])
        report['attempt_count'] -= 1
        files['report.json'] = c.render(c.seal({k: v for k, v in report.items() if k != 'content_sha256'}))
        files['inventory.json'] = c.render(h.inventory({k: v for k, v in files.items() if k != 'inventory.json'}))
        with self.assertRaises(ValueError): c.verify_archive(**self.bundle(files))

    def test_archive_bad_outer_or_inventory_pin_fails(self):
        runner = self.runner()
        runner.run()
        args = self.bundle({p.name: p.read_bytes() for p in runner.store.path.iterdir()})
        for field in ('expected_sha256', 'expected_inventory_sha256'):
            with self.assertRaises(ValueError): c.verify_archive(**dict(args, **{field: 'a' * 64}))

    def test_internal_deadline_preserves_failure_before_hosted_timeout(self):
        runner = self.runner(lambda *_: self.fail('transport called'))
        with patch.object(c, 'MAX_DURATION_NS', 0), self.assertRaises(ValueError): runner.run()
        result = c.parse((runner.store.path / 'report.json').read_bytes())
        self.assertFalse(result['protocol_complete'])
        self.assertEqual(result['attempt_count'], 0)
        self.assertTrue((runner.store.path / 'inventory.json').is_file())


class TransportTests(unittest.TestCase):
    def test_fixed_hosts_headers_length_and_close(self):
        calls = []
        class Response(io.BytesIO):
            status = 200
            def getheader(self, name, default=None): return '2' if name == 'Content-Length' else default
        class Connection:
            def __init__(self, host, timeout): calls.append((host, timeout))
            def request(self, method, path, headers): calls.append((method, path, headers))
            def getresponse(self): return Response(b'{}')
            def close(self): calls.append('closed')
        transport = c.DirectHTTPS(connection_factory=Connection)
        for request in c.daily.identity_requests(DAY):
            out = transport(request, KEYS)
            self.assertTrue(out['complete'])
            self.assertEqual(calls[-1], 'closed')
        self.assertEqual(calls[0], ('data.alpaca.markets', 30))
        self.assertEqual(calls[1][2]['APCA-API-KEY-ID'], KEYS['ALPACA_API_KEY'])
        self.assertIn('apiKey=', calls[4][1])

    def test_order_endpoint_and_credential_override_blocked_before_connection(self):
        transport = c.DirectHTTPS(connection_factory=lambda *_args, **_kwargs: self.fail('connected'))
        request = deepcopy(c.daily.identity_requests(DAY)[0])
        request['url'] = 'https://api.alpaca.markets/v2/orders'
        with self.assertRaises(ValueError): transport(request, KEYS)
        request = deepcopy(c.daily.identity_requests(DAY)[0])
        request['params']['apiKey'] = 'override'
        with self.assertRaises(ValueError): transport(request, KEYS)


class HostedTests(unittest.TestCase):
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
        self.facts = {'head': CODE, 'parents': [h.PARENT], 'parent_commit': h.PARENT,
            'changed_files': ['A\t' + h.CONTRACT_PATH], 'clean': True}
        self.ci = {'id': 456, 'head_sha': CODE, 'path': '.github/workflows/ci.yml', 'event': 'push',
            'status': 'completed', 'conclusion': 'success', 'run_attempt': 1,
            'head_branch': 'phase-3-historical-snapshot', 'repository': {'full_name': 'RoomyRems/momentumbot'}}
        self.ci_jobs = {'total_count': 1, 'jobs': [{'run_id': 456, 'head_sha': CODE, 'name': 'test',
            'status': 'completed', 'conclusion': 'success', 'steps': [{'name': n, 'status': 'completed', 'conclusion': 'success'}
                for n in ('Install package', 'Run tests', 'Compile')]}]}
        self.ref = {'ref': h.REF, 'object': {'type': 'commit', 'sha': CODE}}
        self.artifact = {'id': 789, 'name': f'{h.ID}-consumption-12345-1', 'expired': False,
            'size_in_bytes': 10000, 'digest': 'sha256:' + 'd' * 64,
            'workflow_run': {'id': 12345, 'head_sha': CODE, 'head_branch': 'phase-3-historical-snapshot'}}

    def preflight(self):
        path = self.path / 'preflight'
        path.mkdir()
        for name, value in (('ci.json', self.ci), ('ci-jobs.json', self.ci_jobs), ('consumed-ref.json', self.ref)):
            (path / name).write_bytes(c.render(value))
        self.env['PREFLIGHT_SHA256'] = h.prepare(path, self.contract, self.env, h.d.previous.RUNTIME)
        self.env['PREFLIGHT_ARTIFACT_ID'] = '789'
        return h.d.read_files(path, h.d.PREFLIGHT_FILES)

    def test_preflight_and_launch_exact_code_success(self):
        h.check_launch(self.contract, self.env, self.facts, NOW)
        h.verify_preflight(self.preflight(), self.contract, self.env, h.d.previous.RUNTIME, self.ref, self.artifact)

    def test_wrong_code_event_workflow_parent_or_expiry_fails(self):
        for key, value in (('GITHUB_SHA', 'b' * 40), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
            ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_WORKFLOW_REF', 'wrong'), ('GITHUB_REF', 'refs/heads/main')):
            with self.assertRaises(ValueError): h.check_launch(self.contract, dict(self.env, **{key: value}), self.facts, NOW)
        with self.assertRaises(ValueError): h.check_launch(self.contract, self.env, dict(self.facts, clean=False), NOW)
        with self.assertRaises(ValueError): h.check_launch(self.contract, self.env, self.facts, datetime(2026, 9, 21, tzinfo=timezone.utc))

    def test_changed_preflight_blocks_credentials(self):
        files = self.preflight()
        files['launch.json'] += b' '
        with self.assertRaises(ValueError):
            h.capture(ROOT, self.env, self.facts, NOW, h.d.previous.RUNTIME, files, self.ref, self.artifact,
                output=self.path / 'capture', credential_loader=lambda: self.fail('credentials accessed'), transport=empty, progress=lambda _: None)

    def test_existing_output_blocks_credentials(self):
        files = self.preflight()
        output = self.path / 'capture'
        output.mkdir()
        with self.assertRaises(ValueError):
            h.capture(ROOT, self.env, self.facts, NOW, h.d.previous.RUNTIME, files, self.ref, self.artifact,
                output=output, credential_loader=lambda: self.fail('credentials accessed'), transport=empty, progress=lambda _: None)

    def test_ci_failure_skip_and_wrong_code_fail(self):
        for changes in ({'head_sha': 'b' * 40}, {'run_attempt': 2}, {'conclusion': 'failure'}):
            with self.assertRaises(ValueError): h.d.check_ci(dict(self.ci, **changes), self.ci_jobs, self.env)
        jobs = deepcopy(self.ci_jobs)
        jobs['jobs'][0]['steps'][1]['conclusion'] = 'skipped'
        with self.assertRaises(ValueError): h.d.check_ci(self.ci, jobs, self.env)

    def test_other_consumption_or_expired_artifact_fails(self):
        files = self.preflight()
        with self.assertRaises(ValueError): h.verify_preflight(files, self.contract, self.env, h.d.previous.RUNTIME,
            dict(self.ref, ref=c.b.parent.REF), self.artifact)
        with self.assertRaises(ValueError): h.verify_preflight(files, self.contract, self.env, h.d.previous.RUNTIME,
            self.ref, dict(self.artifact, expired=True))

    def test_complete_hosted_capture_and_original_zip_verification(self):
        files = self.preflight()
        original_capture = c.Capture
        clock = Clock()
        def session(*args, **kwargs):
            return original_capture(*args, **kwargs, clock_ns=clock.read, sleeper=clock.sleep, utc_now=lambda: NOW.isoformat())
        synthetic = panel()
        with patch.object(c.daily, 'load_panel', return_value=synthetic), patch.object(c, 'Capture', side_effect=session):
            result = h.capture(ROOT, self.env, self.facts, NOW, h.d.previous.RUNTIME, files, self.ref, self.artifact,
                output=self.path / 'capture', credential_loader=lambda: KEYS, transport=empty, progress=lambda _: None)
        self.assertTrue(result['protocol_complete'])
        metadata = {}
        for role, directory, identity in (('consumption', 'preflight', 789), ('capture', 'capture', 790)):
            path = self.path / (directory + '.zip')
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
                for member in sorted((self.path / directory).iterdir()): archive.writestr(member.name, member.read_bytes())
            metadata[role] = dict(self.artifact, id=identity, name=f'{h.ID}-{role}-12345-1',
                size_in_bytes=path.stat().st_size, digest='sha256:' + c.sha(path.read_bytes()))
        self.env.update(CAPTURE_ARTIFACT_ID='790', CAPTURE_INVENTORY_SHA256=c.sha((self.path / 'capture/inventory.json').read_bytes()))
        jobs = {'total_count': 3, 'jobs': [{'name': name, 'run_id': 12345, 'head_sha': CODE,
            'status': 'in_progress' if name == 'verify' else 'completed', 'conclusion': None if name == 'verify' else 'success',
            'steps': [{'name': 'Run', 'status': 'completed', 'conclusion': 'success'}]} for name in ('consume', 'capture', 'verify')]}
        with patch.object(c.daily, 'load_panel', return_value=synthetic):
            verified = h.verify(ROOT, self.env, self.facts, NOW, h.d.previous.RUNTIME, self.ref,
                metadata['consumption'], metadata['capture'], jobs, self.path / 'preflight.zip', self.path / 'capture.zip')
        self.assertTrue(verified['hosted_capture_provenance_verified'])
        self.assertEqual(verified['provider_requests_during_verification'], 0)
        self.assertEqual(verified['archive_verification']['attempt_count'], 120)
        self.assertFalse(verified['historical_replay_enabled'])

    def test_full_published_request_union_matches_capture_ceiling(self):
        saved = c.daily.load_panel(ROOT)
        daily_roots = sum(len(c.b.coverage_requests(day)) for day in saved['days'])
        self.assertEqual(daily_roots, 1380)
        self.assertEqual(daily_roots * c.daily.MAX_PAGES + len(saved['days']) * 2 * c.ACTION_PAGES, c.MAX_ATTEMPTS)

    def test_workflow_has_same_code_gate_single_use_and_secrets_only_in_capture_step(self):
        workflow = yaml.safe_load((ROOT / h.WORKFLOW).read_text())
        self.assertEqual(set(workflow['jobs']), {'consume', 'capture', 'verify'})
        self.assertFalse(workflow['concurrency']['cancel-in-progress'])
        secret_steps = [(job, step['name']) for job, spec in workflow['jobs'].items() for step in spec['steps'] if 'secrets.' in str(step)]
        self.assertEqual(secret_steps, [('capture', 'Capture fixed coverage and identity sources once')])
        self.assertEqual(workflow['jobs']['capture']['needs'], 'consume')
        self.assertEqual(workflow['jobs']['verify']['needs'], ['consume', 'capture'])
        for job in workflow['jobs'].values(): self.assertEqual(job['if'], 'github.run_attempt == 1')


if __name__ == '__main__': unittest.main()
