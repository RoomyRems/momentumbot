"""Hosted acceptance is not cross-environment parity or input completeness."""
from copy import deepcopy
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import warnings
from unittest.mock import patch
import zipfile

import verify_sealed_historical_account_hosted_acceptance_v01 as m

ROOT = Path(__file__).resolve().parents[1]


def fixture(gaps=frozenset({(0, 0)})):
    opportunities, catalogs, paths = [], [], []
    for p in range(2):
        pid = f"synthetic-path-{p}"
        initial = {"equity_usd": "100", "buying_power_usd": "100",
            "cumulative_realized_pnl_usd": "0", "cumulative_fees_usd": "0",
            "positions": [], "pending_orders": [], "campaigns": [], "unresolved_inputs": []}
        opening, previous, pairs, slots = deepcopy(initial), None, [], []
        for i in range(2):
            oid, sid = f"opportunity-{p}-{i}", f"session-{p}-{i}"
            unavailable = (p, i) in gaps
            reason = "unavailable_no_fresh_decision_quote" if unavailable else "causal_reference_and_window_available"
            entry = {"input_status": "unavailable" if unavailable else "available", "reason": reason,
                "availability_content_sha256": f"availability-{p}-{i}",
                "quote_request_evidence_sha256": "quotes", "status_request_evidence_sha256": "status"}
            opportunities.append(m.seal({"opportunity_id": oid, "entry": entry,
                "activation": {"symbol": "SYN"}, "source_decision": {"decision_at": f"2025-01-0{i+1}T14:00:00Z"}}))
            ref = {"opportunity_id": oid, **{k: entry[k] for k in
                ("input_status", "reason", "availability_content_sha256")}}
            slot = m.seal({"path_id": pid, "session_id": sid, "session_index": i,
                "trading_date": f"2025-01-0{i+1}", "seed_applied": i == 0, "opportunity_inputs": [ref]})
            slots.append(slot)
            state = deepcopy(opening)
            if unavailable:
                state["unresolved_inputs"].append({"kind": "unavailable_input", "opportunity_id": oid,
                    "reason": reason, "availability_content_sha256": ref["availability_content_sha256"],
                    "blocks_next_session": False})
            runtime = m.seal({"path_id": pid, "session_id": sid,
                "source_slot_content_sha256": slot["content_sha256"],
                "opening_account_state_sha256": m.fingerprint(opening), "failure": None,
                "blocked_before_execution": False, "complete_streams_verified": True,
                "historical_session_scheduler_executed": True, "unconfirmed_entry_order": None,
                "active_original_window": None, "session_gross_realized_pnl_usd": "0",
                "session_net_realized_pnl_usd": "0", "session_fees_usd": "0",
                "opportunity_dispositions": [{**ref, "disposition": "unavailable_input" if unavailable else "blocked_account_lock"}],
                "status": "flat_complete_with_unavailable_inputs" if unavailable else "flat_complete"})
            close = m.seal({"path_id": pid, "session_id": sid, "session_index": i,
                "trading_date": slot["trading_date"], "seed_applied": i == 0,
                "source_slot_content_sha256": slot["content_sha256"],
                "previous_close_content_sha256": previous, "source_runtime_content_sha256": runtime["content_sha256"],
                "account_state": state, "next_session_flat_cash_execution_ready": True})
            pairs.append({"runtime": runtime, "close": close})
            opening, previous = deepcopy(state), close["content_sha256"]
        paths.append(m.seal({"path_id": pid, "sessions": pairs, "session_count": 2,
            "seed_application_count": 1, "initial_account_state": initial,
            "last_close_content_sha256": previous, "path_complete": not any(pp == p for pp, _ in gaps)}))
        catalogs.append({"path_id": pid, "sessions": slots})
    binding = m.seal({"opportunities": opportunities, "paths": catalogs})
    runtime = m.seal({"paths": paths, "source_bindings_content_sha256": binding["content_sha256"]})
    return runtime, binding


def reseal_runtime(runtime):
    for path in runtime["paths"]:
        for pair in path["sessions"]:
            pair["runtime"] = m.seal(pair["runtime"])
            pair["close"]["source_runtime_content_sha256"] = pair["runtime"]["content_sha256"]
            pair["close"] = m.seal(pair["close"])
        path["last_close_content_sha256"] = path["sessions"][-1]["close"]["content_sha256"]
        path.update(m.seal(path))
    return m.seal(runtime)


class CoverageTests(unittest.TestCase):
    def reject(self, mutate):
        runtime, binding = fixture()
        mutate(runtime)
        with self.assertRaises(ValueError):
            m.audit_panel(reseal_runtime(runtime), binding)

    def test_flat_execution_does_not_turn_missing_inputs_into_no_trade(self):
        runtime, binding = fixture()
        before = m.encoded(runtime)
        report = m.audit_panel(runtime, binding)
        self.assertTrue(report["captured_execution_complete"])
        self.assertFalse(report["full_input_coverage_complete"])
        self.assertFalse(report["account_backtest_complete"])
        self.assertEqual(report["population"], {"paths": 2, "sessions": 4,
            "opportunity_references": 4, "unavailable_references": 1, "unique_unavailable_opportunities": 1})
        self.assertFalse(report["unavailable_opportunities"][0]["no_trade_inferred"])
        self.assertEqual(m.encoded(runtime), before)

    def test_prior_gap_conditions_later_fully_available_session(self):
        report = m.audit_panel(*fixture())
        path = report["paths"][0]
        self.assertEqual(path["full_coverage_prefix_sessions"], 0)
        self.assertEqual(path["sessions"][1]["status"], "flat_complete")
        self.assertTrue(path["sessions"][1]["prior_unavailable_history_present"])
        self.assertFalse(path["sessions"][1]["full_input_history_complete"])
        self.assertEqual(report["paths"][1]["full_coverage_prefix_sessions"], 2)

    def test_first_gap_after_available_prefix_and_empty_gap_population(self):
        report = m.audit_panel(*fixture(frozenset({(0, 1)})))
        self.assertEqual(report["paths"][0]["full_coverage_prefix_sessions"], 1)
        complete = m.audit_panel(*fixture(frozenset()))
        self.assertTrue(complete["full_input_coverage_complete"])
        self.assertFalse(complete["account_backtest_complete"])
        self.assertTrue(all(p["financial_metrics_eligible"] is False for p in complete["paths"]))

    def test_missing_path_and_reordered_paths_are_rejected(self):
        self.reject(lambda r: r["paths"].pop())
        self.reject(lambda r: r["paths"].reverse())

    def test_omitted_session_and_duplicate_slot_are_rejected(self):
        self.reject(lambda r: r["paths"][0]["sessions"].pop())
        self.reject(lambda r: r["paths"][0]["sessions"].__setitem__(1, deepcopy(r["paths"][0]["sessions"][0])))

    def test_omitted_or_reclassified_unavailable_opportunity_is_rejected(self):
        self.reject(lambda r: r["paths"][0]["sessions"][0]["runtime"]["opportunity_dispositions"].clear())
        self.reject(lambda r: r["paths"][0]["sessions"][0]["runtime"]["opportunity_dispositions"][0].update(disposition="no_trade"))

    def test_available_input_cannot_be_silently_left_unprocessed(self):
        self.reject(lambda r: r["paths"][1]["sessions"][0]["runtime"]["opportunity_dispositions"][0].update(disposition="unprocessed_available_input"))
        self.reject(lambda r: r["paths"][1]["sessions"][0]["runtime"]["opportunity_dispositions"][0].update(disposition="unknown_disposition"))

    def test_unknown_gap_reason_and_false_complete_status_are_rejected(self):
        self.reject(lambda r: r["paths"][0]["sessions"][0]["runtime"]["opportunity_dispositions"][0].update(reason="unknown"))
        self.reject(lambda r: r["paths"][0]["sessions"][0]["runtime"].update(status="flat_complete"))

    def test_open_positions_pending_orders_and_window_are_rejected(self):
        for key in ("positions", "pending_orders"):
            with self.subTest(key=key):
                self.reject(lambda r: r["paths"][0]["sessions"][0]["close"]["account_state"].update({key: [{"quantity": 1}]}))
        self.reject(lambda r: r["paths"][0]["sessions"][0]["runtime"].update(active_original_window={"end_ns": 10}))
        self.reject(lambda r: r["paths"][0]["sessions"][0]["runtime"].update(unconfirmed_entry_order={"quantity": 1}))

    def test_runtime_failure_and_incomplete_streams_are_rejected(self):
        self.reject(lambda r: r["paths"][0]["sessions"][0]["runtime"].update(failure={"kind": "synthetic"}))
        self.reject(lambda r: r["paths"][0]["sessions"][0]["runtime"].update(complete_streams_verified=False))

    def test_dropped_unavailable_history_is_rejected(self):
        self.reject(lambda r: r["paths"][0]["sessions"][1]["close"]["account_state"].update(unresolved_inputs=[]))

    def test_wrong_cash_fee_carry_or_reseed_is_rejected(self):
        for key in ("equity_usd", "buying_power_usd", "cumulative_realized_pnl_usd", "cumulative_fees_usd"):
            with self.subTest(key=key):
                self.reject(lambda r: r["paths"][0]["sessions"][0]["close"]["account_state"].update({key: "9"}))
        self.reject(lambda r: r["paths"][0]["sessions"][0]["runtime"].update(session_fees_usd="1"))
        self.reject(lambda r: r["paths"][0]["sessions"][1]["close"].update(seed_applied=True))
        self.reject(lambda r: r["paths"][0].update(seed_application_count=True))

    def test_exact_decimal_reconciliation_without_financial_output(self):
        runtime, _ = fixture(frozenset())
        path, pair = runtime["paths"][0], runtime["paths"][0]["sessions"][0]
        pair["runtime"].update(session_gross_realized_pnl_usd="0.30", session_fees_usd="0.10", session_net_realized_pnl_usd="0.20")
        pair["close"]["account_state"].update(equity_usd="100.20", buying_power_usd="100.20",
            cumulative_realized_pnl_usd="0.20", cumulative_fees_usd="0.10")
        m.reconcile_close(path["initial_account_state"], pair["runtime"], pair["close"], [])
        pair["close"]["account_state"]["equity_usd"] = "100.20000000000001"
        with self.assertRaises(ValueError):
            m.reconcile_close(path["initial_account_state"], pair["runtime"], pair["close"], [])

    def test_false_full_path_completion_and_wrong_chain_are_rejected(self):
        self.reject(lambda r: r["paths"][0].update(path_complete=True))
        self.reject(lambda r: r["paths"][0]["sessions"][1]["close"].update(previous_close_content_sha256="wrong"))


class ArtifactAndRegistrationTests(unittest.TestCase):
    def test_seals_canonical_bytes_and_duplicate_json_keys(self):
        value = m.seal({"value": "synthetic"})
        self.assertEqual(m.read_json(m.encoded(value)), value)
        for raw in (json.dumps(value).encode(), b'{"x":1,"x":2}', b'{"value":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                m.read_json(raw)
        with self.assertRaises(ValueError):
            m.checked({**value, "value": "changed"})

    def test_exact_zip_bytes_crc_inventory_and_no_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.zip"
            with zipfile.ZipFile(p, "x") as z:
                z.writestr("a.json", m.encoded(m.seal({"a": 1})))
            spec = {**m.file_spec(p), "members": ["a.json"]}
            self.assertEqual(set(m.verified_zip(p, spec)), {"a.json"})
            self.assertFalse((Path(td) / "a.json").exists())
            for changed in ({**spec, "sha256": "0" * 64}, {**spec, "members": []}):
                with self.assertRaises(ValueError):
                    m.verified_zip(p, changed)

    def test_duplicate_and_unsafe_zip_members_rejected(self):
        for names in (("a", "a"), ("../outside",)):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as td:
                p = Path(td) / "test.zip"
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with zipfile.ZipFile(p, "x") as z:
                        for name in names:
                            z.writestr(name, b"x")
                with self.assertRaises(ValueError):
                    m.verified_zip(p, {**m.file_spec(p), "members": list(names)})

    def test_registration_waives_only_local_rerun_and_is_post_result(self):
        contract = m.registration(ROOT)
        self.assertFalse(contract["full_local_replay_required"])
        self.assertFalse(contract["full_local_reproduction_verified"])
        self.assertFalse(contract["original_contract_rewritten"])
        self.assertTrue(contract["hosted_success_known_before_amendment"])
        self.assertTrue(contract["independent_checker_reused_not_reexecuted"])
        self.assertEqual(contract["expected_runtime_content_sha256"], m.RUNTIME)
        self.assertEqual(contract["required_population"]["unavailable_references"], 162)
        self.assertTrue(all(contract[key] is False for key in m.CLOSED))

    def test_external_commitment_and_changed_implementation_rejected(self):
        contract = m.registration(ROOT)
        with self.assertRaisesRegex(ValueError, "external acceptance"):
            m.check_registration(ROOT, "0" * 64)
        original = m.file_spec
        with patch.object(m, "file_spec", side_effect=lambda p:
                {"bytes": 1, "sha256": "0" * 64} if p == ROOT / m.OWN_FILES[0] else original(p)):
            with self.assertRaisesRegex(ValueError, "external acceptance"):
                m.check_registration(ROOT, contract["content_sha256"])

    def test_cli_has_no_replay_option_and_does_not_overwrite_output(self):
        script = ROOT / m.OWN_FILES[0]
        result = subprocess.run([sys.executable, str(script), "--replay"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments", result.stderr)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "report.json"
            path.write_bytes(b"original")
            result = subprocess.run([sys.executable, str(script), "--output", str(path)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_bytes(), b"original")

    def test_nonfinite_or_float_account_values_rejected(self):
        for value in (float("nan"), "NaN", "Infinity", True, 1.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.number(value)


class EndToEndAcceptanceTests(unittest.TestCase):
    def run_bundle(self, mutation=None):
        runtime, binding = fixture()
        runtime["registration_freeze_content_sha256"] = m.REGISTRATION
        runtime = m.seal(runtime)
        coverage = m.audit_panel(runtime, binding)
        report = {"runtime_content_sha256": runtime["content_sha256"], "verification_passed": True,
            "registration_freeze_content_sha256": m.REGISTRATION,
            "account_backtest_complete": False, "financial_metrics_eligible": False,
            "retrospective_labels_opened": False,
            "totals": {"blocked_sessions": 0, "input_failure_sessions": 0, "executed_sessions": 4}}
        if mutation == "failed_checker":
            report["verification_passed"] = False
        report = m.seal(report)
        native = m.encoded(runtime)
        freeze = m.seal({"file_inventory": {"account-replay.json": {
            "bytes": len(native), "sha256": hashlib.sha256(native).hexdigest()}},
            "document_content_sha256": {"account-replay.json": runtime["content_sha256"]}})
        rows = [(json.dumps(m.seal({"path_id": p["path_id"], "session": s,
            "final_panel": False, "registration_freeze_content_sha256": m.REGISTRATION}),
            sort_keys=True) + "\n").encode() for p in runtime["paths"] for s in p["sessions"]]
        receipt = m.encoded(m.seal({"synthetic_attempt": 1}))
        hosted = {"account-replay/account-replay.json": native,
            "account-replay/independent-verification.json": m.encoded(report),
            "account-replay/freeze-manifest.json": m.encoded(freeze),
            "account-replay-attempt.json": receipt,
            "account-replay-progress.jsonl": b"".join(rows[:-1] if mutation == "missing_progress" else rows)}
        local = {"account-replay-attempt.json": receipt,
            "account-replay-progress.jsonl": rows[0] + (b" " if mutation == "different_prefix" else b"")}
        if mutation == "different_receipt":
            local["account-replay-attempt.json"] = m.encoded(m.seal({"synthetic_attempt": 2}))
        original = {"source-bindings.json": m.encoded(binding)}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            filenames = {"hosted": root / "hosted.zip", "binding": root / "binding.zip",
                "local": root / m.LOCAL_EVIDENCE}
            archive_specs = {}
            for key, members in (("hosted", hosted), ("binding", original), ("local", local)):
                filename = filenames[key]
                filename.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(filename, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, raw in members.items():
                        archive.writestr(name, raw)
                archive_specs[key] = {**m.file_spec(filename), "members": sorted(members)}
            provenance = {"run": {"id": m.HOSTED_RUN, "head_sha": m.IMPLEMENTATION,
                    "run_attempt": 1, "status": "completed", "conclusion": "success"},
                "jobs": [{"id": 102501424811, "conclusion": "success", "steps": [
                    {"status": "completed", "conclusion": "success"}]}],
                "artifacts": [{"id": m.HOSTED_ARTIFACT,
                    "digest": "sha256:" + archive_specs["hosted"]["sha256"]}]}
            if mutation == "rerun":
                provenance["run"]["run_attempt"] = 2
            if mutation == "wrong_artifact":
                provenance["artifacts"][0]["id"] += 1
            if mutation == "pending_checker_step":
                provenance["jobs"][0]["steps"][0]["status"] = "pending"
            p = root / m.PROVENANCE
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(m.encoded(provenance))
            contract = {"required_population": coverage["population"], "required_saved_local_prefix_records": 1,
                "next_gate": "synthetic_coverage_gate"}
            with ExitStack() as stack:
                for name, value in (("ARCHIVES", archive_specs), ("RUNTIME", runtime["content_sha256"]),
                        ("CHECKER", report["content_sha256"]), ("BINDING", binding["content_sha256"])):
                    stack.enter_context(patch.object(m, name, value))
                stack.enter_context(patch.object(m, "check_registration", return_value=contract))
                return m.verify(root, filenames["hosted"], filenames["binding"], "synthetic-contract")

    def test_complete_verification_accepts_hosted_only_without_financial_promotion(self):
        report = self.run_bundle()
        m.checked(report)
        self.assertTrue(report["hosted_runtime_accepted"])
        self.assertFalse(report["full_local_replay_required"])
        self.assertFalse(report["full_local_reproduction_verified"])
        self.assertEqual(report["local_saved_records_byte_identical_to_hosted_prefix"], 1)
        self.assertFalse(report["financial_metrics_eligible"])
        self.assertFalse(report["account_backtest_complete"])
        self.assertFalse(report["replay_executed"])

    def test_failed_checker_or_incomplete_steps_do_not_qualify(self):
        for mutation in ("failed_checker", "pending_checker_step"):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.run_bundle(mutation)

    def test_rerun_or_wrong_artifact_do_not_qualify(self):
        for mutation in ("rerun", "wrong_artifact"):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.run_bundle(mutation)

    def test_missing_progress_or_changed_local_evidence_is_rejected(self):
        for mutation in ("missing_progress", "different_prefix", "different_receipt"):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.run_bundle(mutation)


if __name__ == "__main__":
    unittest.main()
