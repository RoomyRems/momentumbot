from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import yaml

from momentumbot.research import sealed_historical_management_exit_inputs_v01 as m
from tests.test_sealed_historical_management_fill_feedback_v01 import fixture as feedback_fixture, BASE, SECOND

ROOT = Path(__file__).resolve().parents[1]


def fixture(directory, *, tied=False, unknown=False):
    args = feedback_fixture()
    tape, window = deepcopy(args['tape']), deepcopy(args['window'])
    if tied:
        tape['quote_records'].insert(1, deepcopy(tape['quote_records'][0]))
        for i, row in enumerate(tape['quote_records']):
            row['source_record_index'] = i
    if unknown:
        tape['status_records'][0]['is_trading'] = '~'
    op = window['opportunity']['opportunity_id']
    plan = m.runner.derive_exit_plan([window], [tape['quote_request'], tape['status_request']])
    group = plan['groups'][0]
    pair = []
    archive_path = directory / 'sources.zip'
    with zipfile.ZipFile(archive_path, 'w') as archive:
        for ordinal, prefix in enumerate(('quote', 'status')):
            request, rows = tape[prefix + '_request'], tape[prefix + '_records']
            logical = b''.join(m.encoded(r) + b'\n' for r in rows)
            raw = gzip.compress(logical, mtime=0)
            source_path = f'tapes/request-{ordinal:03d}.jsonl.gz'
            archive.writestr(source_path, raw)
            pair.append({'resource_id': group['group_id'] + ':' + request['schema'], 'group_id': group['group_id'],
                'request': request, 'request_content_sha256': m.canonical_fingerprint(request),
                'source_key': 'synthetic', 'source_artifact_id': 123, 'source_zip_sha256': 'a' * 64,
                'source_request_ordinal': ordinal, 'path': f'tapes/synthetic-{ordinal}.jsonl.gz',
                'source_tape': {'path': source_path, 'file_bytes': len(raw), 'file_sha256': hashlib.sha256(raw).hexdigest(),
                    'row_count': len(rows), 'normalized_bytes': len(logical), 'normalized_sha256': hashlib.sha256(logical).hexdigest()}})
    output = directory / 'bundle'
    output.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        for recipe in pair:
            m.copy_source(output, recipe, archive)
    reader = m.ExitInputBundle.__new__(m.ExitInputBundle)
    reader.output = output
    reader._windows = {op: window}
    reader._opportunities = {op: plan['opportunities'][0]}
    reader._resources = {r['resource_id']: r for r in pair}
    reader._groups = {group['group_id']: {'original_group': group,
        'resource_ids': [r['resource_id'] for r in pair], 'execution_tape_content_sha256': m.canonical_fingerprint(tape)}}
    return reader, tape, window, pair, archive_path


class ExitInputsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recipes = m.recipes(ROOT)

    def test_registration_pins_verified_parent_and_closed_runtime(self):
        report = m.validate_registration(ROOT)
        self.assertTrue(report['verification_passed'])
        contract = m.expected_contract(ROOT)
        self.assertEqual(contract['parent_commit_sha'], 'c0ccf773fcc49091682f600c07d991fdd26ab6a8')
        self.assertFalse(contract['historical_runtime_activation_ready'])
        self.assertFalse(contract['historical_execution_authorized'])
        self.assertEqual(contract['provider_calls'], 0)

    def test_registration_rejects_altered_parent_even_if_resealed(self):
        original = m.file_sha
        with patch.object(m, 'file_sha', side_effect=lambda p: '0' * 64 if str(p).endswith(m.CAPTURE_AUDIT) else original(p)):
            with self.assertRaisesRegex(ValueError, 'parent differs'):
                m.validate_registration(ROOT)

    def test_exact_population_uses_all_80_new_and_two_original_sources(self):
        self.assertEqual(len(self.recipes), 82)
        self.assertEqual(len({r['group_id'] for r in self.recipes}), 41)
        self.assertEqual(sum(r['source_key'] == 'exit_result' for r in self.recipes), 80)
        self.assertEqual(sum(r['source_key'] == 'entry_result' for r in self.recipes), 2)
        self.assertEqual(sum(r['source_tape']['row_count'] for r in self.recipes), 2_223_448)
        self.assertEqual(sum(r['source_tape']['normalized_bytes'] for r in self.recipes), 604_286_662)

    def test_reused_XAGE_keeps_original_long_request_and_ordinals(self):
        reused = [r for r in self.recipes if r['source_key'] == 'entry_result']
        self.assertEqual([r['source_request_ordinal'] for r in reused], [78, 79])
        self.assertEqual([r['source_tape']['row_count'] for r in reused], [230703, 4])
        for row in reused:
            self.assertLess(row['required_end_ns'], row['request']['end_ns'])
            self.assertEqual(row['request_content_sha256'], m.canonical_fingerprint(row['request']))

    def test_new_request_with_same_symbol_date_does_not_overwrite_entry_identity(self):
        paths = [r['path'] for r in self.recipes]
        self.assertEqual(len(paths), len(set(paths)))
        for row in self.recipes:
            self.assertIn(row['source_key'], row['path'])

    def test_source_gate_rejects_missing_extra_and_wrong_archive_without_runtime(self):
        with self.assertRaisesRegex(ValueError, 'four source ZIPs'):
            m.verify_sources(ROOT, {})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wrong.zip'
            path.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'source ZIP differs'):
                m.verify_sources(ROOT, {k: path for k in m.source_specs(ROOT)})

    def test_pair_hash_matches_frozen_feedback_payload_with_native_ties(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, tape, _, pair, _ = fixture(Path(directory), tied=True)
            self.assertEqual(m.pair_fingerprint(reader.output, pair), m.canonical_fingerprint(tape))
            quotes = m.adapter.quote_events(tape['quote_records'], tape['quote_request'])
            self.assertEqual(quotes[0].ts_recv_ns, quotes[1].ts_recv_ns)
            self.assertNotEqual(quotes[0].source_record_index, quotes[1].source_record_index)

    def test_copy_preserves_compressed_bytes_exactly_and_is_write_once(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, _, _, pair, source = fixture(Path(directory))
            with zipfile.ZipFile(source) as archive:
                self.assertEqual((reader.output / pair[0]['path']).read_bytes(), archive.read(pair[0]['source_tape']['path']))
                with self.assertRaises(FileExistsError):
                    m.copy_source(reader.output, pair[0], archive)

    def test_source_file_changed_before_copy_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, _, _, pair, source = fixture(Path(directory))
            pair[0]['source_tape']['file_sha256'] = '0' * 64
            with zipfile.ZipFile(source) as archive, self.assertRaisesRegex(ValueError, 'before copy'):
                m.copy_source(reader.output, pair[0], archive)

    def test_final_truncation_is_detected_before_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, _, _, pair, _ = fixture(Path(directory))
            path = reader.output / pair[0]['path']
            path.write_bytes(path.read_bytes()[:-8])
            with self.assertRaisesRegex(ValueError, 'final tape differs'):
                m.pair_fingerprint(reader.output, pair)

    def test_gzip_eof_or_crc_failure_cannot_be_hidden_by_rehashed_file_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, _, _, pair, _ = fixture(Path(directory))
            path = reader.output / pair[0]['path']
            raw = path.read_bytes()[:-8]
            path.write_bytes(raw)
            pair[0]['source_tape'].update(file_sha256=hashlib.sha256(raw).hexdigest(), file_bytes=len(raw))
            with self.assertRaises((EOFError, gzip.BadGzipFile)):
                m.pair_fingerprint(reader.output, pair)

    def test_normalized_count_or_hash_mismatch_cannot_be_resealed(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, _, _, pair, _ = fixture(Path(directory))
            for field, value in (('row_count', 1), ('normalized_bytes', 1), ('normalized_sha256', '0' * 64)):
                changed = deepcopy(pair)
                changed[0]['source_tape'][field] = value
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'normalized source tape differs'):
                    m.pair_fingerprint(reader.output, changed)

    def test_paths_traversal_absolute_duplicate_slashes_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name in ('../outside.jsonl.gz', '/tapes/a.jsonl.gz', 'tapes/../a.jsonl.gz', 'tapes//a.jsonl.gz', 'tapes/a\\b.jsonl.gz'):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'unsafe'):
                    m.safe_tape_path(output, name)
            (output / 'tapes').symlink_to(output, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symbolic link'):
                m.safe_tape_path(output, 'tapes/a.jsonl.gz')

    def test_cannot_write_output_over_repository_sources(self):
        with self.assertRaisesRegex(ValueError, 'frozen repository'):
            m.write_bundle(ROOT, ROOT / 'research', {})

    def test_single_write_detects_short_write(self):
        with tempfile.TemporaryDirectory() as directory:
            stream = io.BytesIO()
            class ShortWrite:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def write(self, raw):
                    stream.write(raw[:1])
                    return 1
            with patch.object(Path, 'open', return_value=ShortWrite()), self.assertRaisesRegex(OSError, 'short exit source write'):
                m.write_once(Path(directory) / 'data', b'123')

    def test_partial_copy_failure_is_retained_and_never_frozen(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            _, _, _, pair, source = fixture(directory)
            output = directory / 'failed'
            with ExitStack() as stack:
                stack.enter_context(patch.object(m, 'validate_registration'))
                stack.enter_context(patch.object(m, 'verify_sources'))
                stack.enter_context(patch.object(m, 'recipes', return_value=pair))
                stack.enter_context(patch.object(m, 'copy_source', side_effect=OSError('private provider details')))
                with self.assertRaisesRegex(ValueError, 'partial evidence retained'):
                    m.write_bundle(ROOT, output, {'synthetic': source})
            failure = m.frozen(output / 'composition-failure.json')
            self.assertFalse(failure['exit_input_source_bundle_verified'])
            self.assertFalse(failure['historical_execution_authorized'])
            self.assertNotIn('private provider details', json.dumps(failure))
            self.assertFalse((output / 'freeze-manifest.json').exists())

    def test_reader_keeps_identical_payload_across_repeated_sell_decisions(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, expected, window, _, _ = fixture(Path(directory))
            op = window['opportunity']['opportunity_id']
            a, sha_a = reader.execution_tape(op, BASE + SECOND, expected_window_content_sha256=m.canonical_fingerprint(window))
            b, sha_b = reader.execution_tape(op, BASE + 2 * SECOND, expected_window_content_sha256=m.canonical_fingerprint(window))
            self.assertEqual(a, expected)
            self.assertEqual(a, b)
            self.assertEqual(sha_a, sha_b)
            self.assertEqual(set(a), {'quote_request', 'quote_records', 'status_request', 'status_records'})

    def test_reader_returns_detached_data_and_detects_changed_source_before_access(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, expected, window, pair, _ = fixture(Path(directory))
            op, pin = window['opportunity']['opportunity_id'], m.canonical_fingerprint(window)
            value, _ = reader.execution_tape(op, BASE + SECOND, expected_window_content_sha256=pin)
            value['quote_records'][0]['bid_size'] = 999999
            reader.opportunity(op)['group_id'] = None
            again, _ = reader.execution_tape(op, BASE + SECOND, expected_window_content_sha256=pin)
            self.assertEqual(again, expected)
            path = reader.output / pair[0]['path']
            path.write_bytes(path.read_bytes()[:-3])
            with self.assertRaises((ValueError, EOFError, gzip.BadGzipFile)):
                reader.execution_tape(op, BASE + SECOND, expected_window_content_sha256=pin)

    def test_unavailable_entry_remains_visible_and_cannot_be_rescued(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, _, window, _, _ = fixture(Path(directory))
            op = window['opportunity']['opportunity_id']
            reader._opportunities[op].update(entry_input_status='unavailable', group_id=None)
            self.assertEqual(reader.opportunity(op)['entry_input_status'], 'unavailable')
            with self.assertRaisesRegex(ValueError, 'unavailable entry'):
                reader.execution_tape(op, BASE + SECOND, expected_window_content_sha256=m.canonical_fingerprint(window))

    def test_wrong_opportunity_or_original_window_pin_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, _, window, _, _ = fixture(Path(directory))
            with self.assertRaisesRegex(ValueError, 'unregistered'):
                reader.opportunity('unregistered')
            with self.assertRaisesRegex(ValueError, 'window pin'):
                reader.execution_tape(window['opportunity']['opportunity_id'], BASE + SECOND, expected_window_content_sha256='0' * 64)

    def test_exit_tail_cannot_borrow_later_time_from_merged_or_XAGE_source(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, _, window, _, _ = fixture(Path(directory))
            op, pin = window['opportunity']['opportunity_id'], m.canonical_fingerprint(window)
            group = next(iter(reader._groups.values()))['original_group']
            member = group['members'][0]
            for timestamp in (BASE, member['first_possible_exit_decision_ns'] - 1, member['last_covered_exit_decision_ns'] + 1, window['end_ns']):
                with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                    reader.execution_tape(op, timestamp, expected_window_content_sha256=pin)
            for timestamp in (member['first_possible_exit_decision_ns'], member['last_covered_exit_decision_ns']):
                value, _ = reader.execution_tape(op, timestamp, expected_window_content_sha256=pin)
                self.assertTrue(value['quote_records'])

    def test_boolean_float_and_nonpositive_exit_clock_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, _, window, _, _ = fixture(Path(directory))
            for timestamp in (True, float(BASE + SECOND), 0, -1):
                with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                    reader.execution_tape(window['opportunity']['opportunity_id'], timestamp,
                        expected_window_content_sha256=m.canonical_fingerprint(window))

    def test_bounded_capture_preserves_ordinals_and_excludes_later_source_quotes(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, tape, window, _, _ = fixture(Path(directory), tied=True)
            op, at = window['opportunity']['opportunity_id'], BASE + SECOND
            projected = reader.capture_window(op, at, expected_window_content_sha256=m.canonical_fingerprint(window))
            self.assertFalse(projected['historical_execution_authorized'])
            self.assertTrue(projected['quotes'])
            indices = {r['source_record_index'] for r in projected['quotes']}
            self.assertNotIn(0, indices)
            for row in projected['quotes']:
                self.assertLessEqual(row['ts_recv_ns'], at + m.projection.POST_QUOTE_NS)
                self.assertEqual(row['source_request_sha256'], m.canonical_fingerprint(tape['quote_request']))

    def test_complete_sources_do_not_imply_known_status_or_executable_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, _, window, _, _ = fixture(Path(directory), unknown=True)
            projected = reader.capture_window(window['opportunity']['opportunity_id'], BASE + SECOND,
                expected_window_content_sha256=m.canonical_fingerprint(window))
            self.assertEqual(projected['quotes'], [])
            self.assertFalse(projected['historical_execution_authorized'])

    def test_constructor_requires_external_pin_and_committed_metadata(self):
        for pin in ('', 'a', None, True):
            with self.subTest(pin=pin), self.assertRaisesRegex(ValueError, 'external exact'):
                m.ExitInputBundle(ROOT, ROOT / m.BUNDLE_PATH, expected_manifest_content_sha256=pin)
        with patch.object(m, 'validate_registration'), patch.object(m, 'check_committed_metadata', return_value={'freeze_manifest_content_sha256': 'b' * 64}):
            with self.assertRaisesRegex(ValueError, "caller's frozen parent"):
                m.ExitInputBundle(ROOT, ROOT / m.BUNDLE_PATH, expected_manifest_content_sha256='a' * 64)

    def test_historical_runtime_gate_stays_closed(self):
        with self.assertRaisesRegex(ValueError, 'dependencies unresolved'):
            m.runner.require_historical_runtime_ready(ROOT)

    def test_workflow_is_read_only_fixed_artifacts_and_has_no_provider_secrets(self):
        source = (ROOT / m.WORKFLOW_PATH).read_text()
        workflow = yaml.safe_load(source)
        self.assertEqual(workflow['permissions'], {'contents': 'read', 'actions': 'read'})
        self.assertNotIn('secrets.', source)
        self.assertNotIn('workflow_dispatch', source)
        for spec in m.source_specs(ROOT).values():
            self.assertIn(f"artifacts/{spec['artifact_id']}/zip", source)
        self.assertIn('--check-committed', source)
        self.assertIn(m.CHECKER_PATH, source)

    def test_cli_installs_offline_guard_before_import_and_blocks_missing_sources(self):
        source = (ROOT / m.SCRIPT_PATH).read_text()
        self.assertLess(source.index('sys.addaudithook'), source.index('from momentumbot.research'))
        completed = subprocess.run([sys.executable, str(ROOT / m.SCRIPT_PATH), '--build'], cwd=ROOT,
            capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2)
        self.assertIn('all four exact source ZIPs', completed.stderr)

    def test_entrypoints_have_no_undefined_globals(self):
        from scripts.check_recovery_entrypoints_v13 import undefined_globals
        for name in (m.MODULE_PATH, m.SCRIPT_PATH, m.CHECKER_PATH):
            self.assertEqual(undefined_globals((ROOT / name).read_text(), name), set(), name)

    def test_independent_verifier_rejects_source_ordinal_rewriting(self):
        from scripts import verify_sealed_historical_management_exit_inputs_v01 as checker
        with tempfile.TemporaryDirectory() as directory:
            _, tape, _, pair, _ = fixture(Path(directory))
            tape['quote_records'][0]['source_record_index'] = 1
            logical = b''.join(m.encoded(r) + b'\n' for r in tape['quote_records'])
            raw = gzip.compress(logical, mtime=0)
            receipt = {**pair[0]['source_tape'], 'file_bytes': len(raw), 'file_sha256': hashlib.sha256(raw).hexdigest(),
                'normalized_bytes': len(logical), 'normalized_sha256': hashlib.sha256(logical).hexdigest()}
            with self.assertRaisesRegex(ValueError, 'ordinal differs'):
                checker.records(raw, tape['quote_request'], receipt)


if __name__ == '__main__':
    unittest.main()
