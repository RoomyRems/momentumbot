from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from momentumbot.research import sealed_historical_source_binding_v01 as m
from tests.test_sealed_historical_account_scheduler_v01 import spec, empty_program, attach

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    position = spec()
    op = position["entry_input"]["window"]["opportunity"]
    decision = position["entry_input"]["source_decision"]
    row = {"symbol": op["symbol"], "decision_time": decision["candidate_qualified_at"],
        "candidate_completed_bar_present": True, "price": 10.0, "cumulative_volume": 1_000_000,
        "exact_same_time_rvol": 10.0, "percent_gain": 50.0, "estimated_float_shares": 5_000_000,
        "has_provider_news_as_of": True, "top_gainer_rank": 1}
    activation = {"activation_id": op["activation_id"], "symbol": op["symbol"],
        "candidate_qualified_at": decision["candidate_qualified_at"],
        "eligible_strategy_profile_ids": list(op["eligible_strategy_profile_ids"]),
        "scanner_record_content_sha256": m.canonical_fingerprint(row), "scanner_snapshot_content_sha256": "a" * 64}
    return position, activation, row


def candidate(position, activation, row, profile=None):
    op = position["entry_input"]["window"]["opportunity"]
    return m.bind_candidate(row, activation, op, profile or op["eligible_strategy_profile_ids"][0])


def archive(directory, members):
    path = directory / "source.zip"
    with zipfile.ZipFile(path, "w") as output:
        for name, value in members:
            output.writestr(name, value)
    raw = path.read_bytes()
    return path, {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


class BindingMechanicsTests(unittest.TestCase):
    def test_exact_causal_candidate_uses_original_features(self):
        p, a, row = fixture()
        result = candidate(p, a, row)
        self.assertEqual(result["relative_volume"], 10)
        self.assertEqual(result["top_gainer_rank"], 1)
        self.assertEqual(result["quality"], "a_quality")
        self.assertEqual(set(result), m.parent.scheduler.CANDIDATE_FIELDS)

    def test_later_scanner_row_cannot_replace_original_activation(self):
        p, a, row = fixture()
        row["top_gainer_rank"] = 2
        with self.assertRaisesRegex(ValueError, "commitment"):
            candidate(p, a, row)

    def test_rehashed_later_timestamp_is_rejected(self):
        p, a, row = fixture()
        row["decision_time"] = m.pd.Timestamp(row["decision_time"]) + m.pd.Timedelta(seconds=1)
        row["decision_time"] = row["decision_time"].isoformat()
        a["scanner_record_content_sha256"] = m.canonical_fingerprint(row)
        with self.assertRaisesRegex(ValueError, "activation time"):
            candidate(p, a, row)

    def test_wrong_symbol_or_activation_rejected(self):
        for key in ("symbol", "activation_id"):
            p, a, row = fixture()
            a[key] += "X"
            with self.subTest(key=key), self.assertRaises(ValueError):
                candidate(p, a, row)

    def test_profile_membership_not_inferred_from_better_features(self):
        p, a, row = fixture()
        with self.assertRaisesRegex(ValueError, "membership"):
            candidate(p, a, row, "invented-profile")
        a["eligible_strategy_profile_ids"] = []
        with self.assertRaisesRegex(ValueError, "membership"):
            candidate(p, a, row)

    def test_known_row_must_still_pass_frozen_profile(self):
        p, a, row = fixture()
        row["price"] = 100
        a["scanner_record_content_sha256"] = m.canonical_fingerprint(row)
        with self.assertRaisesRegex(ValueError, "qualifies"):
            candidate(p, a, row)

    def test_retrospective_input_is_rejected_even_with_new_hash(self):
        p, a, row = fixture()
        row["ross_fill"] = 10
        a["scanner_record_content_sha256"] = m.canonical_fingerprint(row)
        with self.assertRaisesRegex(ValueError, "retrospective"):
            candidate(p, a, row)

    def test_nan_and_boolean_candidate_features_rejected(self):
        for key, value in (("price", float("nan")), ("top_gainer_rank", True), ("cumulative_volume", True)):
            p, a, row = fixture()
            row[key] = value
            with self.subTest(key=key), self.assertRaises((ValueError, TypeError)):
                a["scanner_record_content_sha256"] = m.canonical_fingerprint(row)
                candidate(p, a, row)

    def test_decision_keeps_exact_nanoseconds_and_plan(self):
        p, a, _ = fixture()
        value = m.bind_decision(p["entry_input"]["window"], p["entry_input"]["source_decision"], a)
        self.assertEqual(value, p["entry_input"]["source_decision"])
        value["plan"]["stop_price"] = 0
        self.assertNotEqual(value, p["entry_input"]["source_decision"])

    def test_replaced_micro_decision_rejected(self):
        for key, value in (("plan_id", "other-plan"), ("decision_at", "2025-05-30T12:00:00Z")):
            p, a, _ = fixture()
            p["entry_input"]["source_decision"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "commitment"):
                m.bind_decision(p["entry_input"]["window"], p["entry_input"]["source_decision"], a)

    def test_additional_decision_outcome_rejected(self):
        p, a, _ = fixture()
        p["entry_input"]["source_decision"]["realized_pnl"] = 100
        with self.assertRaisesRegex(ValueError, "exact original"):
            m.bind_decision(p["entry_input"]["window"], p["entry_input"]["source_decision"], a)

    def test_duplicate_identities_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            m.unique([{"id": "x"}, {"id": "x"}], "id")

    def test_json_duplicate_and_nonfinite_rejected(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                m._json(raw)

    def test_archive_whole_bytes_required_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, pin = archive(root, [("source.json", "{}")])
            pin["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "original bytes"):
                m.extract_archive(path, pin, root / "out")
            self.assertFalse((root / "out").exists())

    def test_archive_rejects_path_traversal_absolute_and_symlink(self):
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for name in ("../escape", "/absolute", "x\\escape", "x/./escape", link):
            with self.subTest(name=str(name)), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path, pin = archive(root, [(name, "other")])
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    m.extract_archive(path, pin, root / "out")
                self.assertFalse((root / "out").exists())

    def test_archive_valid_member_extracted_exactly_and_write_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, pin = archive(root, [("tapes/rows", "exact\nbytes\n")])
            m.extract_archive(path, pin, root / "out")
            self.assertEqual((root / "out/tapes/rows").read_bytes(), b"exact\nbytes\n")
            with self.assertRaisesRegex(ValueError, "new nonsymlink"):
                m.extract_archive(path, pin, root / "out")

    def test_carry_gaps_preserve_state_and_do_not_imply_flatness(self):
        program = empty_program()
        paths = [{"path_id": program["path_id"], "sessions": program["slots"]}]
        dependencies = m.carry_dependencies(paths)
        self.assertEqual(len(dependencies), 29)
        for value in dependencies:
            self.assertIsNone(value["previous_close_content_sha256"])
            self.assertFalse(value["flat_state_inferred"])
            self.assertFalse(value["unchanged_units_inferred_from_split_prices"])
            self.assertFalse(value["source_request_authorized"])
            self.assertIn("no_extension_or_retry", value["expired_window_execution"])

    def test_carry_cannot_skip_preceding_session(self):
        p = empty_program()
        with self.assertRaisesRegex(ValueError, "exact preceding"):
            m.carry_dependencies([{"path_id": p["path_id"], "sessions": [p["slots"][0], p["slots"][2]]}])


def reader_fixture():
    p, activation, row = fixture()
    program = attach(empty_program(), 0, p)
    op = p["entry_input"]["window"]["opportunity"]
    binding = m.seal({"opportunity_id": op["opportunity_id"], "window": p["entry_input"]["window"],
        "source_decision": p["entry_input"]["source_decision"], "candidates": {
            program["slots"][0]["profile_id"]: candidate(p, activation, row)},
        "entry": {"input_status": "unavailable", "reason": "synthetic_missing_original"}})
    source = object.__new__(m.OriginalSources)
    source._temporary = "synthetic-test"
    source._manifest = m.seal({"paths": [{"path_id": program["path_id"], "sessions": program["slots"]}],
        "opportunities": [binding]})
    return source, program["path_id"], op["opportunity_id"]


class SourceAccessTests(unittest.TestCase):
    def test_unavailable_context_preserved_without_entry_access(self):
        reader, path, oid = reader_fixture()
        sha = reader.manifest()["content_sha256"]
        value = reader.context(path, oid, expected_manifest_sha256=sha)
        self.assertEqual(value["entry_input_status"], "unavailable")
        self.assertFalse(value["historical_runtime_authorized"])
        with self.assertRaisesRegex(ValueError, "cannot be rescued"):
            reader.entry_tape(path, oid, expected_manifest_sha256=sha)

    def test_source_manifest_requires_external_pin(self):
        reader, path, oid = reader_fixture()
        with self.assertRaisesRegex(ValueError, "pin differs"):
            reader.context(path, oid, expected_manifest_sha256="0" * 64)

    def test_context_requires_original_account_path(self):
        reader, _, oid = reader_fixture()
        with self.assertRaisesRegex(ValueError, "account path"):
            reader.context("foreign", oid, expected_manifest_sha256=reader.manifest()["content_sha256"])

    def test_mutating_returned_manifest_cannot_change_source(self):
        reader, path, oid = reader_fixture()
        value = reader.manifest()
        value["opportunities"][0]["entry"]["input_status"] = "available"
        self.assertEqual(reader.context(path, oid, expected_manifest_sha256=value["content_sha256"])["entry_input_status"], "unavailable")

    def test_closed_reader_rejects_access(self):
        reader, path, oid = reader_fixture()
        reader._temporary = None
        with self.assertRaisesRegex(ValueError, "not open"):
            reader.context(path, oid, expected_manifest_sha256="0" * 64)


class RegistrationTests(unittest.TestCase):
    def test_exact_parent_and_registration_reconstruct(self):
        self.assertTrue(m.verify_bundle(ROOT, ROOT / m.OUTPUT_PATH)["verification_passed"])

    def test_all_original_account_dependencies_preserved(self):
        paths = m.frozen(ROOT / m.projection.ACCOUNT_PLAN)["paths"]
        self.assertEqual(len(paths), 12)
        self.assertEqual(sum(len(p["sessions"]) for p in paths), 360)
        self.assertEqual(len(m.carry_dependencies(paths)), 348)
        self.assertEqual(sum(len(s["opportunity_inputs"]) for p in paths for s in p["sessions"]), 744)

    def test_registration_cannot_claim_verified_original_data_or_runtime(self):
        value = m.frozen(ROOT / m.OUTPUT_PATH / "readiness-report.json")
        self.assertFalse(value["source_bytes_verified_in_this_registration"])
        self.assertFalse(value["historical_runtime_authorized"])
        self.assertFalse(value["account_or_fill_simulation_executed"])
        self.assertFalse(value["corporate_action_source_provenance_verified"])

    def test_original_archive_inventory_literal_pins(self):
        self.assertEqual(len(m.SOURCES), 5)
        self.assertEqual(m.SOURCES["scanner"]["sha256"], m.scanner.SOURCE_ZIP_SHA256)
        audit = m.frozen(ROOT / "research/data-audits/sealed-historical-management-inputs-v0.1-independent-verification.json")
        self.assertEqual(m.SOURCES["management"]["sha256"], audit["complete_bundle_zip_sha256"])

    def test_wrong_registration_pin_rejected_before_archive_access(self):
        with patch.object(m, "checked_archive") as open_archive:
            with self.assertRaisesRegex(ValueError, "registration pin"):
                m.OriginalSources(ROOT, {}, expected_registration_sha256="0" * 64)
            open_archive.assert_not_called()

    def test_missing_archives_cannot_be_synthetic_fallback(self):
        pin = m.frozen(ROOT / m.OUTPUT_PATH / "freeze-manifest.json")["content_sha256"]
        with self.assertRaisesRegex(ValueError, "five exact"):
            m.OriginalSources(ROOT, {}, expected_registration_sha256=pin)

    def test_output_cannot_write_into_repository(self):
        with self.assertRaisesRegex(ValueError, "repository"):
            m.write_files(ROOT, ROOT / "research/new-source-artifact", {"a": b"x"})

    def test_offline_cli_registration_and_undefined_globals(self):
        result = subprocess.run([sys.executable, str(ROOT / m.SCRIPT_PATH), "--verify"],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["verification_passed"])
        from check_recovery_entrypoints_v13 import undefined_globals
        for name in (m.MODULE_PATH, m.SCRIPT_PATH, m.CHECKER_PATH):
            self.assertEqual(undefined_globals((ROOT / name).read_text(), name), set())


class IndependentCheckerTests(unittest.TestCase):
    def test_independent_timestamp_preserves_nanoseconds_and_offsets(self):
        from verify_sealed_historical_source_binding_v01 import ns
        stamp = "2025-05-30T07:00:01.123456789-04:00"
        self.assertEqual(ns(stamp), int(m.pd.Timestamp(stamp).value))
        with self.assertRaises(ValueError):
            ns("2025-05-30T07:00:00")

    def test_independent_candidate_projection_matches_both_fixed_profiles(self):
        from verify_sealed_historical_source_binding_v01 import candidate as independent
        p, a, row = fixture()
        row["price"] = 5
        for news in (True, False):
            row["has_provider_news_as_of"] = news
            a["scanner_record_content_sha256"] = m.canonical_fingerprint(row)
            for profile in m.PROFILES:
                a["eligible_strategy_profile_ids"] = list(m.PROFILES)
                p["entry_input"]["window"]["opportunity"]["eligible_strategy_profile_ids"] = list(m.PROFILES)
                with self.subTest(profile=profile, news=news):
                    self.assertEqual(independent(row, profile), candidate(p, a, row, profile))

    def test_independent_checker_rejects_forged_candidate_profile(self):
        from verify_sealed_historical_source_binding_v01 import candidate as independent
        _, _, row = fixture()
        for field, value in (("price", 100), ("candidate_completed_bar_present", False), ("top_gainer_rank", 4)):
            changed = {**row, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                independent(changed, "current-small-account-2026")

    def test_independent_module_does_not_import_runtime_or_strategy(self):
        import ast
        tree = ast.parse((ROOT / m.CHECKER_PATH).read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(name and name.startswith("momentumbot") for name in imports))


if __name__ == "__main__":
    unittest.main()
