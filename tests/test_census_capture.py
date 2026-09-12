from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from momentumbot.research import census_capture as m
from tests.test_early_pullback_census_v01 import Clock, SECRET, STAMP, body, row, synthetic_reply, archive_files

ROOT = Path(__file__).resolve().parents[1]


def mixed_reply(request, credential):
    reply = synthetic_reply(request, credential)
    if request['kind'] != 'current_type_dictionary':
        reply['body'] = body([row('ACRV' if request['page'] == 1 else 'ACRpC')],
            'next' if request['page'] == 1 else None)
    return reply


def session(output, transport=mixed_reply, **kwargs):
    clock = Clock()
    return m.CaptureSession(m.seal({'contract_id': m.ID, 'limits': m.legacy.limits()}),
        output=output, transport=transport, credential=SECRET, clock_ns=clock.read,
        sleeper=clock.sleep, utc_now=lambda: STAMP, **kwargs), clock


def repin(files):
    files['inventory.json'] = m.render(m.seal({'contract_id': m.ID, 'files': {
        n: {'bytes': len(raw), 'sha256': m.sha(raw)} for n, raw in files.items() if n != 'inventory.json'}}))


class CensusCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def capture(self, transport=mixed_reply, **kwargs):
        runner, clock = session(self.root / 'capture', transport, **kwargs)
        result = runner.run()
        return runner, clock, result

    def complete(self):
        runner, _, _ = self.capture()
        return runner, {p.name: p.read_bytes() for p in runner.store.path.iterdir()}

    def verify(self, runner, files, name='capture.zip'):
        path = self.root / name
        return m.verify_archive(path, contract=runner.contract, **archive_files(path, files))

    def test_complete_mixed_case_capture_and_raw_archive_replay(self):
        runner, clock, result = self.capture()
        self.assertTrue(result['protocol_complete'])
        self.assertEqual(result['attempt_count'], 61)
        self.assertEqual(clock.sleeps, [12.5] * 60)
        files = {p.name: p.read_bytes() for p in runner.store.path.iterdir()}
        verified = self.verify(runner, files)
        self.assertEqual(verified['verified_member_count'], 247)
        self.assertTrue(all(d['state'] == 'exhausted' and d['accepted_rows'] == 2 for d in verified['dates']))
        for key, value in m.legacy.BOUNDARY.items(): self.assertEqual(verified[key], value)

    def test_original_quarantined_provider_page_survives_capture_and_replay(self):
        with zipfile.ZipFile(ROOT / m.diagnostic.BASE / 'hosted-result.zip') as archive:
            original = archive.read('response.body.json')
        def transport(request, credential):
            reply = synthetic_reply(request, credential)
            if request['kind'] == 'pit_membership_page' and request['trading_date'] == m.legacy.DATES[0]:
                reply['body'] = original if request['page'] == 1 else body([row('ZZZZ_SYNTHETIC')])
            return reply
        runner, _, result = self.capture(transport)
        files = {p.name: p.read_bytes() for p in runner.store.path.iterdir()}
        self.assertEqual(files['0001.body.json'], original)
        self.assertEqual(result['dates'][0]['accepted_rows'], 1001)
        self.assertEqual(self.verify(runner, files)['attempt_count'], 32)

    def test_intent_is_durable_before_transport_and_no_secret_is_retained(self):
        calls = []
        def transport(request, credential):
            self.assertTrue((self.root / 'capture' / f'{len(calls):04d}.intent.json').is_file())
            calls.append(request)
            return mixed_reply(request, credential)
        runner, _, _ = self.capture(transport)
        self.assertEqual(len(calls), 61)
        self.assertFalse(any(SECRET.encode() in p.read_bytes() for p in runner.store.path.iterdir()))

    def test_safe_rejected_page_retained_with_fixed_reason_and_no_retry(self):
        bad = body([row('ACRpC'), row('ACRV')])
        def transport(request, credential):
            reply = synthetic_reply(request, credential)
            if request['kind'] == 'pit_membership_page': reply['body'] = bad
            return reply
        runner, _, result = self.capture(transport)
        self.assertEqual(result['attempt_count'], 2)
        self.assertEqual(result['failure']['detail'], 'provider page order regressed')
        self.assertEqual((runner.store.path / '0001.body.json').read_bytes(), bad)
        self.assertFalse((runner.store.path / '0001.normalized.json').exists())
        self.assertFalse(result['protocol_complete'])
        self.assertEqual(result['dates'][0]['accepted_pages'], 0)

    def test_cross_page_order_failure_keeps_body_projection_and_receipt(self):
        def transport(request, credential):
            reply = mixed_reply(request, credential)
            if request['kind'] == 'pit_membership_page':
                reply['body'] = body([row('ACRpC' if request['page'] == 1 else 'ACRV')],
                    'next' if request['page'] == 1 else None)
            return reply
        runner, _, result = self.capture(transport)
        self.assertEqual(result['attempt_count'], 3)
        self.assertEqual(result['failure']['detail'], 'cross-page ordering regression')
        receipt = m.parse_json((runner.store.path / '0002.receipt.json').read_bytes())
        self.assertTrue(receipt['body_retained'] and receipt['normalized_retained'])
        self.assertEqual(result['dates'][0]['accepted_pages'], 1)

    def test_unicode_and_duplicate_key_credential_echo_is_not_saved(self):
        escaped = ''.join('\\u%04x' % ord(c) for c in SECRET)
        raw = ('{"status":"OK","echo":"' + escaped + '","echo":"safe","results":[]}').encode()
        runner, _, result = self.capture(lambda *_: {'status': 200, 'body': raw, 'complete': True, 'encoding': 'identity'})
        self.assertEqual(result['attempt_count'], 1)
        self.assertEqual(result['failure']['reason'], 'credential_echo')
        self.assertFalse(any(p.name.endswith('.body.json') for p in runner.store.path.iterdir()))

    def test_non_json_provider_error_retains_hash_only(self):
        runner, _, result = self.capture(lambda *_: {'status': 200, 'body': b'not-json', 'complete': True, 'encoding': 'identity'})
        self.assertEqual(result['failure']['reason'], 'uninspectable_json')
        receipt = m.parse_json((runner.store.path / '0000.receipt.json').read_bytes())
        self.assertEqual(receipt['body_sha256'], m.sha(b'not-json'))
        self.assertFalse(receipt['body_retained'])

    def test_http_incomplete_encoding_and_size_errors_stop_once(self):
        cases = [({'status': 403}, 'http_error'), ({'complete': False}, 'incomplete_body'),
            ({'encoding': 'gzip'}, 'content_encoding'), ({'body': b'x' * (m.legacy.MAX_BODY + 1)}, 'response_too_large')]
        for i, (change, reason) in enumerate(cases):
            reply = dict(synthetic_reply(m.legacy.type_request(), SECRET), **change)
            runner, _ = session(self.root / f'case{i}', lambda *_: reply)
            result = runner.run()
            self.assertEqual(result['attempt_count'], 1)
            self.assertEqual(result['failure']['reason'], reason)

    def test_transport_exception_never_discloses_text_or_retries(self):
        def transport(*_): raise RuntimeError(SECRET)
        runner, _, result = self.capture(transport)
        self.assertEqual(result['attempt_count'], 1)
        self.assertEqual(result['failure']['reason'], 'transport_or_retention_error')
        self.assertFalse(any(SECRET.encode() in p.read_bytes() for p in runner.store.path.iterdir()))

    def test_no_restart_or_output_reuse(self):
        runner, _, _ = self.capture()
        with self.assertRaises(ValueError): runner.run()
        with self.assertRaises(FileExistsError): session(runner.store.path)

    def test_interruption_preserves_intent_and_failure_inventory(self):
        def transport(*_): raise KeyboardInterrupt()
        runner, _ = session(self.root / 'capture', transport)
        with self.assertRaises(KeyboardInterrupt): runner.run()
        self.assertTrue((runner.store.path / '0000.intent.json').is_file())
        self.assertTrue((runner.store.path / 'inventory.json').is_file())
        self.assertEqual(m.parse_json((runner.store.path / 'report.json').read_bytes())['failure']['reason'], 'interrupted')

    def test_failed_pacing_does_not_start_second_request(self):
        runner, _ = session(self.root / 'capture')
        runner.sleeper = lambda _: None
        with self.assertRaisesRegex(ValueError, 'pacing'): runner.run()
        self.assertEqual(runner.attempts, 1)

    def test_partial_archive_cannot_claim_completion(self):
        runner, _, _ = self.capture(lambda *_: {'status': 429, 'body': b'{}', 'complete': True, 'encoding': 'identity'})
        files = {p.name: p.read_bytes() for p in runner.store.path.iterdir()}
        with self.assertRaises(ValueError): self.verify(runner, files)

    def test_raw_order_witness_tamper_fails_even_if_resealed(self):
        runner, files = self.complete()
        projected = m.parse_json(files['0001.normalized.json'])
        projected['provider_tickers'] = ['ACRpC']
        files['0001.normalized.json'] = m.render(projected)
        receipt = m.parse_json(files['0001.receipt.json'])
        receipt['normalized_sha256'] = m.legacy.fingerprint(projected)
        files['0001.receipt.json'] = m.render(m.seal({k: v for k, v in receipt.items() if k != 'content_sha256'}))
        repin(files)
        with self.assertRaisesRegex(ValueError, 'raw/normalized'): self.verify(runner, files)

    def test_changed_raw_member_is_detected_under_new_outer_pin(self):
        runner, files = self.complete()
        files['0001.body.json'] += b' '
        with self.assertRaisesRegex(ValueError, 'member byte'): self.verify(runner, files)

    def test_wrong_outer_inventory_or_contract_pin_fails(self):
        runner, files = self.complete()
        path = self.root / 'capture.zip'
        pins = archive_files(path, files)
        for key in ('expected_sha256', 'expected_inventory_sha256'):
            with self.assertRaises(ValueError): m.verify_archive(path, contract=runner.contract, **dict(pins, **{key: '0' * 64}))
        with self.assertRaises(ValueError): m.verify_archive(path, contract={}, **pins)

    def test_extra_missing_unsafe_members_and_false_terminal_report_fail(self):
        runner, files = self.complete()
        cases = [dict(files, extra=b'{}'), {n: b for n, b in files.items() if n != '0001.body.json'}, dict(files, **{'../escape': b'{}'})]
        false_report = deepcopy(files)
        report = m.parse_json(false_report['report.json'])
        report['attempt_count'] += 1
        false_report['report.json'] = m.render(m.seal({k: v for k, v in report.items() if k != 'content_sha256'}))
        repin(false_report)
        cases.append(false_report)
        for i, values in enumerate(cases):
            with self.assertRaises(ValueError): self.verify(runner, values, f'bad{i}.zip')

    def test_exact_601_request_capture_and_archive_bound(self):
        def transport(request, credential):
            reply = synthetic_reply(request, credential)
            if request['kind'] == 'pit_membership_page':
                page = request['page']
                reply['body'] = body([row(f'S{page:02d}')], str(page) if page < 20 else None)
            return reply
        runner, _, result = self.capture(transport)
        self.assertEqual(result['attempt_count'], 601)
        files = {p.name: p.read_bytes() for p in runner.store.path.iterdir()}
        self.assertEqual(self.verify(runner, files)['verified_member_count'], 2407)

    def test_required_page_21_is_failed_not_truncated_success(self):
        def transport(request, credential):
            reply = synthetic_reply(request, credential)
            if request['kind'] == 'pit_membership_page': reply['body'] = body([row(f'S{request["page"]:02d}')], str(request['page']))
            return reply
        _, _, result = self.capture(transport)
        self.assertEqual(result['attempt_count'], 21)
        self.assertFalse(result['protocol_complete'])
        self.assertEqual(result['dates'][0]['accepted_pages'], 19)

    def test_payload_limit_preserves_failed_receipt_without_extra_call(self):
        with patch.object(m.legacy, 'MAX_PAYLOAD', 10):
            runner, _, result = self.capture()
        self.assertEqual(result['attempt_count'], 1)
        self.assertEqual(result['failure']['reason'], 'retention_limit')
        self.assertTrue((runner.store.path / '0000.receipt.json').is_file())
