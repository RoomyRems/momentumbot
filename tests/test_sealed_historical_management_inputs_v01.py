from __future__ import annotations

from contextlib import ExitStack, contextmanager
import copy
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

import pandas as pd
import yaml

from momentumbot.research import sealed_historical_management_inputs_v01 as m

ROOT = Path(__file__).resolve().parents[1]
BASE = int(pd.Timestamp('2025-05-30T14:00:00Z').value)


def trade(offset, identity=1):
    return {"t": pd.Timestamp(BASE + offset, unit='ns', tz='UTC').isoformat(),
        "p": 4.0, "s": 25, "i": identity, "x": "Q", "z": "C", "c": ["@"]}


def lines(rows):
    return [m.reuse._canonical_line(r) for r in rows]


def segment(key, start, end, source_rows, first, selected_count, ordinal_basis):
    selected = [] if not selected_count else lines(source_rows)[first:first + selected_count]
    body = b''.join((str(first + i).encode() + b':' if ordinal_basis else b'') + raw for i, raw in enumerate(selected))
    all_raw = b''.join(lines(source_rows))
    return {"source_key": key, "source_artifact_id": 1 if key == 'prefix' else 2, "source_zip_sha256": 'a' * 64,
        "source_request_id": key + '-request', "source_path": key + '.jsonl.gz',
        "source_tape_file_sha256": hashlib.sha256(gzip.compress(all_raw, mtime=0)).hexdigest(),
        "source_tape_logical_sha256": hashlib.sha256(all_raw).hexdigest(), "source_tape_record_count": len(source_rows),
        "first_source_record_ordinal": first, "record_count": selected_count, "start_ns": BASE + start, "end_ns": BASE + end,
        "expected_selection_basis": 'decimal_source_ordinal_colon_exact_canonical_row' if ordinal_basis else 'exact_canonical_rows',
        "expected_selection_sha256": hashlib.sha256(body).hexdigest()}


def fixture(parent, *, prefix=None, tail=None, empty=False):
    prefix = [trade(-1), trade(0, 2), trade(0, 1)] if prefix is None else prefix
    tail = [trade(1_000_000_000, 3), trade(2_999_999_999, 4)] if tail is None else tail
    if empty:
        prefix, tail = [], []
    segments = [segment('prefix', 0, 1_000_000_000, prefix, 1 if prefix else None, max(0, len(prefix) - 1), True),
                segment('tail', 1_000_000_000, 3_000_000_000, tail, 0 if tail else None, len(tail), False)]
    recipe = {"resource_id": "synthetic:sip_transactions", "resource": "sip_transactions", "kind": "sip_trades",
        "management_request_id": "synthetic", "trading_date": "2025-05-30", "symbol": "SYNTHETIC",
        "start_ns": BASE, "end_ns": BASE + 3_000_000_000, "end_exclusive": True, "feed": "sip", "asof": "2025-05-30",
        "adjustment": None, "opportunity_ids": ['op-1', 'op-2'], "path": "tapes/synthetic-sip_trades.jsonl.gz", "segments": segments}
    paths = {}
    for key, rows in (('prefix', prefix), ('tail', tail)):
        path = parent / (key + '.zip')
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr(key + '.jsonl.gz', gzip.compress(b''.join(lines(rows)), mtime=0))
        paths[key] = path
    return recipe, paths, prefix, tail


class ManagementInputsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recipes = m.derive_recipes(ROOT)

    def compose(self, parent, recipe, paths, name='bundle'):
        output = parent / name
        output.mkdir()
        with ExitStack() as stack:
            archives = {key: stack.enter_context(zipfile.ZipFile(path)) for key, path in paths.items()}
            receipt = m.compose_tape(output, recipe, archives)
        return output, receipt

    def test_registration_binds_verified_capture_parent_without_runtime_authority(self):
        result = m.validate_registration(ROOT)
        contract = m.expected_contract(ROOT)
        self.assertTrue(result['verification_passed'])
        self.assertEqual(contract['parent_commit_sha'], '536226a134aa9863130205b954065f24c89ce599')
        self.assertEqual(contract['logical_resources'], 112)
        for key, value in m.BOUNDARY.items():
            self.assertEqual(contract[key], value)

    def test_parent_audit_edit_cannot_be_resealed(self):
        original = m.file_sha
        with patch.object(m, 'file_sha', side_effect=lambda p: '0' * 64 if str(p).endswith(m.CAPTURE_AUDIT) else original(p)):
            with self.assertRaisesRegex(ValueError, 'parent differs'):
                m.validate_registration(ROOT)

    def test_exact_112_resources_use_122_disjoint_segments_and_all_ten_tails(self):
        self.assertEqual(len(self.recipes), 112)
        self.assertEqual(len({r['management_request_id'] for r in self.recipes}), 56)
        self.assertEqual(sum(len(r['segments']) for r in self.recipes), 122)
        self.assertEqual(sum(s['source_key'] == 'missing_tails' for r in self.recipes for s in r['segments']), 10)
        self.assertEqual(len({oid for r in self.recipes for oid in r['opportunity_ids']}), 109)
        for recipe in self.recipes:
            m.validate_segments(recipe['start_ns'], recipe['end_ns'], recipe['segments'])

    def test_parent_counts_predict_all_rows_without_reclassifying_prints(self):
        self.assertEqual(sum(s['record_count'] for r in self.recipes if r['resource'] == 'sip_transactions' for s in r['segments']), 3_654_215)
        self.assertEqual(sum(s['record_count'] for r in self.recipes if r['resource'] == 'raw_sip_1m_bars' for s in r['segments']), 975)
        self.assertFalse(m.expected_contract(ROOT)['management_trade_eligibility_filter_applied'])
        self.assertFalse(m.expected_contract(ROOT)['warmup_is_management_input'])

    def test_exact_10am_join_preserves_nanosecond_endpoints(self):
        for recipe in self.recipes:
            if len(recipe['segments']) == 2:
                self.assertEqual(recipe['segments'][0]['end_ns'], recipe['segments'][1]['start_ns'])
                self.assertEqual(recipe['segments'][1]['start_ns'], pd.Timestamp(recipe['trading_date'] + 'T14:00:00Z').value)
                self.assertEqual(recipe['end_ns'], recipe['segments'][1]['end_ns'])

    def test_gap_overlap_extension_reversal_and_float_boundaries_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe, _, _, _ = fixture(Path(directory))
            for key, value in (('start_ns', BASE + 1_000_000_001), ('start_ns', BASE + 999_999_999),
                               ('end_ns', BASE + 3_000_000_001), ('end_ns', BASE + 1_000_000_000), ('start_ns', float(BASE))):
                segments = copy.deepcopy(recipe['segments'])
                segments[1][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    m.validate_segments(recipe['start_ns'], recipe['end_ns'], segments)

    def test_empty_and_source_ordinal_type_errors_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe, _, _, _ = fixture(Path(directory))
            for key, value in (('record_count', True), ('first_source_record_ordinal', -1),
                               ('first_source_record_ordinal', 100), ('source_tape_record_count', True)):
                segments = copy.deepcopy(recipe['segments'])
                segments[0][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    m.validate_segments(recipe['start_ns'], recipe['end_ns'], segments)

    def test_composition_copies_bytes_and_maps_original_ordinals_including_ties(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe, paths, prefix, tail = fixture(parent)
            output, receipt = self.compose(parent, recipe, paths)
            expected = b''.join(lines(prefix[1:] + tail))
            self.assertEqual(gzip.decompress((output / receipt['path']).read_bytes()), expected)
            self.assertEqual(receipt['record_count'], 4)
            self.assertEqual(receipt['logical_sha256'], hashlib.sha256(expected).hexdigest())
            self.assertEqual([(s['first_source_record_ordinal'], s['composed_start_ordinal'], s['composed_end_ordinal_exclusive'])
                             for s in receipt['segments']], [(1, 0, 2), (0, 2, 4)])
            source_lines = [(1, 'prefix-request', 1 + i, raw) for i, raw in enumerate(lines(prefix[1:]))]
            source_lines += [(2, 'tail-request', i, raw) for i, raw in enumerate(lines(tail))]
            lineage = b''.join(f'{aid}:{rid}:{ordinal}:'.encode() + raw for aid, rid, ordinal, raw in source_lines)
            self.assertEqual(receipt['source_lineage_sha256'], hashlib.sha256(lineage).hexdigest())

    def test_compression_is_deterministic_and_does_not_embed_path_or_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe, paths, _, _ = fixture(parent)
            left, _ = self.compose(parent, recipe, paths, 'left')
            right, _ = self.compose(parent, recipe, paths, 'right')
            raw = (left / recipe['path']).read_bytes()
            self.assertEqual(raw, (right / recipe['path']).read_bytes())
            self.assertEqual(raw[3], 0)
            self.assertEqual(raw[4:8], b'\0' * 4)

    def test_complete_compressor_is_written_once_and_synced_after_finalization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tape.gz'
            with patch.object(m.os, 'fsync', wraps=m.os.fsync) as sync:
                with m.finalized_gzip_file(path) as tape:
                    tape.write(b'one\ntwo\n')
                    self.assertFalse(path.exists())
                sync.assert_called_once()
            self.assertEqual(gzip.decompress(path.read_bytes()), b'one\ntwo\n')
            with self.assertRaises(FileExistsError):
                with m.finalized_gzip_file(path):
                    self.fail('write-once tape was opened')

    def test_empty_complete_resources_keep_receipts_and_valid_empty_tapes(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe, paths, _, _ = fixture(parent, empty=True)
            output, receipt = self.compose(parent, recipe, paths)
            self.assertTrue(receipt['complete_request_envelope'])
            self.assertTrue(receipt['empty_source_evidence'])
            self.assertEqual(receipt['record_count'], 0)
            self.assertEqual(gzip.decompress((output / recipe['path']).read_bytes()), b'')
            self.assertEqual([s['composed_end_ordinal_exclusive'] for s in receipt['segments']], [0, 0])

    def test_tail_cannot_copy_an_event_at_exact_exclusive_end(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe, paths, _, _ = fixture(parent, tail=[trade(3_000_000_000)])
            with self.assertRaisesRegex(ValueError, 'interval'):
                self.compose(parent, recipe, paths)

    def test_source_order_and_parent_selection_commitment_cannot_change(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe, paths, _, _ = fixture(parent, prefix=[trade(-1), trade(1, 1), trade(0, 2)])
            with self.assertRaisesRegex(ValueError, 'order'):
                self.compose(parent, recipe, paths)
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe, paths, _, _ = fixture(parent)
            recipe['segments'][0]['expected_selection_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'parent evidence'):
                self.compose(parent, recipe, paths)

    def test_truncated_source_cannot_supply_missing_selected_records(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe, paths, _, _ = fixture(parent)
            with zipfile.ZipFile(paths['tail'], 'w') as archive:
                archive.writestr('tail.jsonl.gz', gzip.compress(b'', mtime=0))
            with self.assertRaisesRegex(ValueError, 'ended before'):
                self.compose(parent, recipe, paths)

    def test_tape_path_traversal_and_symlink_parent_fail_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe, paths, _, _ = fixture(parent)
            for index, path in enumerate(('../escape.gz', '/escape.gz', 'tapes/../escape.gz', 'tapes\\escape.gz', '', 'tapes')):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    self.compose(parent, {**recipe, 'path': path}, paths, f'bad-{index}')
            output = parent / 'linked'
            output.mkdir()
            (output / 'tapes').symlink_to(parent, target_is_directory=True)
            with ExitStack() as stack:
                archives = {key: stack.enter_context(zipfile.ZipFile(path)) for key, path in paths.items()}
                with self.assertRaisesRegex(ValueError, 'symbolic link'):
                    m.compose_tape(output, recipe, archives)

    def test_existing_composition_and_repo_input_targets_are_rejected_before_source_access(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(m, 'verify_sources') as verify:
            output = Path(directory)
            with self.assertRaises(FileExistsError):
                m.write_bundle(ROOT, output, {})
            with self.assertRaisesRegex(ValueError, 'frozen repository'):
                m.write_bundle(ROOT, ROOT / 'research' / 'unsafe', {})
            verify.assert_not_called()

    def test_source_verification_rejects_missing_or_wrong_archives_before_reconstruction(self):
        with self.assertRaisesRegex(ValueError, 'three source'):
            m.verify_sources(ROOT, {})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.zip'
            path.write_bytes(b'wrong')
            with patch.object(m.reuse, 'verify_bundle') as verify, self.assertRaisesRegex(ValueError, 'source ZIP'):
                m.verify_sources(ROOT, {key: path for key in m.source_specs(ROOT)})
            verify.assert_not_called()

    def test_opportunity_index_preserves_109_identities_23_unavailable_and_all_30_dates(self):
        receipts = [{**r, 'record_count': sum(s['record_count'] for s in r['segments']), 'retained_bytes': 0,
                     'empty_source_evidence': False} for r in self.recipes]
        docs = m.documents(ROOT, receipts, m.seal({'fixture': True}))
        parent, _, _ = m.parent_documents(ROOT)
        index = docs['opportunity-input-index.json']
        self.assertEqual([{k: v for k, v in op.items() if k != 'resource_ids'} for op in index['opportunity_windows']], parent['opportunity_windows'])
        self.assertEqual(index['dates'], parent['dates'])
        ready = docs['readiness-report.json']
        self.assertEqual((ready['date_count'], ready['opportunity_count'], ready['unavailable_entry_opportunity_count']), (30, 109, 23))
        self.assertEqual(len(ready['no_decision_dates']), 5)
        self.assertEqual(ready['missing_resource_count'], 0)
        for key, value in m.BOUNDARY.items():
            self.assertEqual(ready[key], value)

    def test_omitted_or_reordered_resource_receipts_do_not_create_readiness(self):
        for receipts in (self.recipes[:-1], self.recipes[::-1]):
            with self.assertRaisesRegex(ValueError, 'ordered resource'):
                m.documents(ROOT, receipts, m.seal({'fixture': True}))

    @contextmanager
    def synthetic_bundle(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            parent = Path(directory)
            recipe, paths, _, _ = fixture(parent)
            root = parent / 'repo'
            root.mkdir()
            for name in (m.MODULE_PATH, m.SCRIPT_PATH, m.WORKFLOW_PATH, m.TEST_PATH, m.CONTRACT_PATH):
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / name).read_bytes())
            management = m.seal({'requests': [{'request_id': 'synthetic'}],
                'dates': [{'trading_date': '2025-05-30', 'opportunity_count': 2}],
                'opportunity_windows': [{'opportunity': {'opportunity_id': oid}, 'request_id': 'synthetic',
                    'start_ns': BASE, 'end_ns': BASE + 3_000_000_000, 'entry_input_status': 'unavailable',
                    'entry_input_reason': 'frozen-unavailable', 'availability_content_sha256': 'b' * 64}
                    for oid in ('op-1', 'op-2')]})
            stack.enter_context(patch.object(m, 'validate_registration'))
            stack.enter_context(patch.object(m, 'verify_sources', return_value=m.seal({'synthetic_source_proof': True})))
            stack.enter_context(patch.object(m, 'source_specs', return_value={key: {'zip_sha256': m.file_sha(path)} for key, path in paths.items()}))
            stack.enter_context(patch.object(m, 'derive_recipes', return_value=[recipe]))
            stack.enter_context(patch.object(m, 'parent_documents', return_value=(management, {}, {})))
            yield root, root / m.BUNDLE_PATH, paths, recipe

    def test_end_to_end_build_freeze_reader_and_complete_reconstruction(self):
        with self.synthetic_bundle() as (root, output, paths, _):
            progress = []
            result = m.write_bundle(root, output, paths, progress.append)
            self.assertEqual(len(result['file_inventory']), 6)
            self.assertEqual(progress, [{'composed_resources': 1, 'total_resources': 1, 'composed_records': 4}])
            m.freeze_metadata(root, output)
            self.assertEqual(m.check_committed_metadata(root, output), result)
            self.assertEqual(m.verify_bundle(root, output, paths), result)
            reader = m.ManagementInputBundle(root, output,
                expected_manifest_content_sha256=result['freeze_manifest_content_sha256'])
            self.assertEqual(len(list(reader.iter_records('op-1', 'sip_transactions'))), 4)
            with self.assertRaises(FileExistsError):
                m.freeze_metadata(root, output)
            self.assertFalse((output / 'composition-failure.json').exists())

    def test_bundle_tamper_or_extra_file_cannot_match_committed_metadata(self):
        with self.synthetic_bundle() as (root, output, paths, recipe):
            m.write_bundle(root, output, paths)
            m.freeze_metadata(root, output)
            tape = output / recipe['path']
            original = tape.read_bytes()
            tape.write_bytes(original + b'tamper')
            with self.assertRaises(ValueError):
                m.check_committed_metadata(root, output)
            tape.write_bytes(original)
            extra = output / 'extra.json'
            extra.write_bytes(b'{}')
            with self.assertRaises(ValueError):
                m.check_bundle_files(output)
            extra.unlink()
            metadata = output / 'readiness-report.json'
            metadata.write_bytes(metadata.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'committed freeze'):
                m.check_committed_metadata(root, output)

    def test_composition_failure_keeps_partial_evidence_without_success_manifest(self):
        with self.synthetic_bundle() as (root, output, paths, recipe):
            recipe['segments'][1]['expected_selection_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'partial evidence retained'):
                m.write_bundle(root, output, paths)
            failure = m.frozen(output / 'composition-failure.json')
            self.assertEqual(failure['exception_class'], 'ValueError')
            self.assertEqual(failure['completed_resources'], 0)
            self.assertTrue((output / recipe['path']).is_file())
            self.assertFalse((output / 'freeze-manifest.json').exists())
            self.assertFalse((root / m.SNAPSHOT_PATH).exists())

    def test_final_file_change_cannot_be_sealed_as_a_successful_inventory(self):
        with self.synthetic_bundle() as (root, output, paths, _):
            compose = m.compose_tape
            def change_after_receipt(*args):
                receipt = compose(*args)
                path = args[0] / receipt['path']
                path.write_bytes(path.read_bytes()[:-10])
                return receipt
            with patch.object(m, 'compose_tape', side_effect=change_after_receipt):
                with self.assertRaisesRegex(ValueError, 'partial evidence retained'):
                    m.write_bundle(root, output, paths)
            self.assertTrue((output / 'composition-failure.json').exists())
            self.assertFalse((output / 'freeze-manifest.json').exists())

    def test_resealed_file_inventory_does_not_override_original_logical_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe, paths, _, _ = fixture(parent)
            output, receipt = self.compose(parent, recipe, paths)
            receipt['logical_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'logical content'):
                m.verify_tape_receipts(output, [receipt], m.accounts.availability._inventory(output))

    def test_raw_minute_bars_reject_unaligned_or_repeated_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe, paths, _, _ = fixture(parent)
            recipe['kind'] = 'session_1m_raw'
            with self.assertRaisesRegex(ValueError, 'minute bar identity'):
                self.compose(parent, recipe, paths)
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe, paths, _, _ = fixture(parent, prefix=[trade(-1), trade(1)])
            recipe['kind'] = 'session_1m_raw'
            with self.assertRaisesRegex(ValueError, 'minute bar identity'):
                self.compose(parent, recipe, paths)

    def reader_fixture(self, parent, *, empty_prefix=False):
        recipe, paths, _, _ = fixture(parent, prefix=[] if empty_prefix else None)
        output, receipt = self.compose(parent, recipe, paths)
        op = {'opportunity': {'opportunity_id': 'op-1'}, 'resource_ids': {'sip_transactions': recipe['resource_id']},
              'start_ns': BASE + 1_000_000_000, 'end_ns': BASE + 2_000_000_000,
              'entry_input_status': 'unavailable', 'entry_input_reason': 'frozen-unavailable'}
        m.capture.write_json(output / 'management-input-manifest.json', m.seal({'resources': [receipt]}))
        m.capture.write_json(output / 'opportunity-input-index.json', m.seal({'opportunity_windows': [op]}))
        with patch.object(m, 'validate_registration'), patch.object(m, 'check_committed_metadata', return_value={'freeze_manifest_content_sha256': 'f' * 64}):
            reader = m.ManagementInputBundle(ROOT, output, expected_manifest_content_sha256='f' * 64)
        return reader, recipe, output

    def test_reader_clips_shared_window_and_preserves_tail_source_ordinals(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, _, _ = self.reader_fixture(Path(directory))
            records = list(reader.iter_records('op-1', 'sip_transactions'))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['timestamp_ns'], BASE + 1_000_000_000)
            self.assertEqual((records[0]['composed_record_ordinal'], records[0]['source_record_ordinal']), (2, 0))
            self.assertEqual(records[0]['source_artifact_id'], 2)
            self.assertEqual(reader.opportunity('op-1')['entry_input_status'], 'unavailable')

    def test_reader_handles_empty_prefix_and_returns_independent_opportunity_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, _, _ = self.reader_fixture(Path(directory), empty_prefix=True)
            records = list(reader.iter_records('op-1', 'sip_transactions'))
            self.assertEqual(records[0]['composed_record_ordinal'], 0)
            op = reader.opportunity('op-1')
            op['entry_input_status'] = 'available'
            self.assertEqual(reader.opportunity('op-1')['entry_input_status'], 'unavailable')

    def test_reader_rejects_unknown_opportunity_resource_and_changed_tape(self):
        with tempfile.TemporaryDirectory() as directory:
            reader, recipe, output = self.reader_fixture(Path(directory))
            for oid, resource in (('unknown', 'sip_transactions'), ('op-1', 'quotes')):
                with self.subTest(oid=oid, resource=resource), self.assertRaises(ValueError):
                    list(reader.iter_records(oid, resource))
            with (output / recipe['path']).open('ab') as stream:
                stream.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'changed'):
                list(reader.iter_records('op-1', 'sip_transactions'))

    def test_reader_requires_external_manifest_pin_even_for_resealed_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'caller must pin'):
                m.ManagementInputBundle(ROOT, Path(directory), expected_manifest_content_sha256='short')
            with patch.object(m, 'validate_registration'), patch.object(m, 'check_committed_metadata', return_value={'freeze_manifest_content_sha256': 'a' * 64}):
                with self.assertRaisesRegex(ValueError, "caller's frozen parent"):
                    m.ManagementInputBundle(ROOT, Path(directory), expected_manifest_content_sha256='b' * 64)

    def test_cli_registration_runs_with_early_offline_guard(self):
        result = subprocess.run([sys.executable, str(ROOT / m.SCRIPT_PATH), '--validate-registration'],
            cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['verification_passed'])
        script = (ROOT / m.SCRIPT_PATH).read_text()
        self.assertLess(script.index('sys.addaudithook(deny_external_io)'), script.index('from momentumbot.research import'))

    def test_hosted_workflow_has_no_market_credentials_or_capture_and_checks_committed_freeze(self):
        workflow = yaml.safe_load((ROOT / m.WORKFLOW_PATH).read_text())
        self.assertEqual(workflow['permissions'], {'contents': 'read', 'actions': 'read'})
        steps = workflow['jobs']['compose']['steps']
        text = (ROOT / m.WORKFLOW_PATH).read_text()
        self.assertNotIn('secrets.', text)
        self.assertNotIn('ALPACA', text)
        self.assertIn('--check-committed', text)
        self.assertEqual(steps[-1]['with']['retention-days'], 90)
        self.assertNotIn('if', steps[-1])


if __name__ == '__main__':
    unittest.main()
