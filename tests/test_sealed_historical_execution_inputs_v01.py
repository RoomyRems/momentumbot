from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import pandas as pd

from momentumbot.research import sealed_historical_execution_inputs_v01 as registration
from momentumbot.research.prospective_market_input_capture import validate_opportunity_manifest

ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    "repo_root": ROOT,
    "micro_root": ROOT / "research/runtime/sealed-historical-micro-v0.1",
    "scanner_root": ROOT / "research/runtime/sealed-historical-scanner-activation-v0.2",
}
FROZEN_OUTPUT = ROOT / "research/runtime/sealed-historical-execution-input-plan-v0.1"


def write_sealed(path: Path, payload: dict) -> None:
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    path.write_text(json.dumps(registration.seal(unsigned), indent=2, sort_keys=True) + "\n")


class HistoricalExecutionInputRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = registration.build_registration(**INPUTS)

    def test_committed_bundle_rederives_from_every_exact_parent_file(self):
        report = registration.validate_registration(output_root=FROZEN_OUTPUT, **INPUTS)
        self.assertTrue(report["verification_passed"])
        self.assertEqual(report["request_count"], 90)
        self.assertEqual(report["opportunity_count"], 109)
        self.assertEqual(report["provider_calls"], 0)

    def test_every_source_decision_is_preserved_without_account_selection(self):
        observed = self.bundle["opportunity-manifest.json"]["opportunities"]
        by_plan = {row["plan_id"]: row for row in observed}
        self.assertEqual(len(by_plan), 109)
        total = 0
        for day in registration.EXPECTED_DATES:
            daily = json.loads((INPUTS["micro_root"] / "dates" / f"{day}.json").read_text())
            for row in daily["decisions"]:
                retained = by_plan[row["plan_id"]]
                self.assertEqual(retained["activation_id"], row["activation_id"])
                self.assertEqual(retained["eligible_strategy_profile_ids"], row["eligible_strategy_profile_ids"])
                self.assertEqual(retained["decision_ts_ns"], pd.Timestamp(row["decision_at"]).value)
                self.assertEqual(retained["source_decision_content_sha256"], registration.canonical_fingerprint(row))
                self.assertNotIn("plan", retained)
                total += 1
        self.assertEqual(total, 109)
        self.assertEqual(sum(len(r["eligible_strategy_profile_ids"]) == 2 for r in observed), 15)

    def test_real_nanosecond_window_and_same_time_distinct_activations(self):
        rows = [r for r in self.bundle["opportunity-manifest.json"]["opportunities"]
                if r["trading_date"] == "2025-05-30" and r["symbol"] == "GITS"]
        self.assertEqual(len(rows), 6)
        self.assertEqual({r["decision_ts_ns"] for r in rows}, {
            1748609823147734566, 1748609843463881835, 1748609850199660995,
        })
        self.assertEqual(len({r["activation_id"] for r in rows}), 2)
        requests = {r["schema"]: r for r in self.bundle["request-manifest.json"]["requests"]
                    if r["request_id"].startswith("2025-05-30-GITS-")}
        self.assertEqual(requests["mbp-1"]["start_ns"], 1748609823047734566)
        self.assertEqual(requests["mbp-1"]["end_ns"], 1748609850749660996)
        self.assertEqual(requests["status"]["start_ns"], 1748563200000000000)
        self.assertEqual(requests["status"]["end_ns"], requests["mbp-1"]["end_ns"])

    def test_all_dates_and_genuine_empty_dates_remain_explicit(self):
        rows = self.bundle["opportunity-manifest.json"]["dates"]
        self.assertEqual([r["trading_date"] for r in rows], list(registration.EXPECTED_DATES))
        empty = [r for r in rows if r["decision_count"] == 0]
        self.assertEqual([r["trading_date"] for r in empty], [
            "2025-06-03", "2025-06-05", "2025-06-16", "2025-06-17", "2025-06-20",
        ])
        self.assertTrue(all(r["input_plan_status"] == "not_applicable_no_micro_decisions" for r in empty))
        self.assertEqual(sum(r["no_trigger_activation_count"] for r in rows), 144)
        self.assertEqual(sum(r["unavailable_activation_count"] for r in rows), 0)

    def test_historical_bundle_cannot_be_passed_off_as_prospective(self):
        with self.assertRaises(ValueError):
            validate_opportunity_manifest(self.bundle["opportunity-manifest.json"])

    def test_opportunity_id_excludes_profile_selection_but_retains_profile_provenance(self):
        daily = json.loads((INPUTS["micro_root"] / "dates/2025-05-30.json").read_text())
        before = registration._opportunities(daily)
        changed = deepcopy(daily)
        changed["decisions"][0]["eligible_strategy_profile_ids"] = ["current-general-2026"]
        after = registration._opportunities(changed)
        self.assertEqual({r["opportunity_id"] for r in before}, {r["opportunity_id"] for r in after})
        self.assertNotEqual(before, after)

    def test_rehashed_parent_change_is_rejected_before_plan_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "micro"
            shutil.copytree(INPUTS["micro_root"], root)
            path = root / "dates/2025-05-30.json"
            daily = json.loads(path.read_text())
            daily["decisions"][0]["decision_at"] = "2025-05-30T12:57:03.147734567+00:00"
            write_sealed(path, daily)
            with self.assertRaisesRegex(ValueError, "parent bytes"):
                registration.build_registration(**{**INPUTS, "micro_root": root})

    def test_missing_source_date_is_not_zero_opportunities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "micro"
            shutil.copytree(INPUTS["micro_root"], root)
            (root / "dates/2025-06-05.json").unlink()
            with self.assertRaisesRegex(ValueError, "inventory"):
                registration.build_registration(**{**INPUTS, "micro_root": root})

    def test_rehashed_output_request_or_identity_tampering_is_rejected(self):
        mutations = [
            ("request-manifest.json", lambda x: x["requests"].pop()),
            ("request-manifest.json", lambda x: x["requests"][0].update(start_ns=x["requests"][0]["start_ns"] - 1)),
            ("request-manifest.json", lambda x: x["requests"][0].update(dataset="XNAS.BASIC")),
            ("opportunity-manifest.json", lambda x: x["opportunities"][0].update(symbol="OTHER")),
            ("opportunity-manifest.json", lambda x: x["opportunities"][0].update(eligible_strategy_profile_ids=[])),
            ("freeze-manifest.json", lambda x: x["boundary"].update(provider_calls=False)),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "output"
                shutil.copytree(FROZEN_OUTPUT, root)
                path = root / name
                payload = json.loads(path.read_text())
                mutate(payload)
                write_sealed(path, payload)
                with self.assertRaisesRegex(ValueError, "exact historical derivation"):
                    registration.validate_registration(output_root=root, **INPUTS)

    def test_rehashed_retrospective_and_account_fields_are_rejected(self):
        for field in ("ross_label", "fill_price", "pnl", "selected_scenario", "account_id"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "output"
                shutil.copytree(FROZEN_OUTPUT, root)
                path = root / "opportunity-manifest.json"
                payload = json.loads(path.read_text())
                payload["opportunities"][0][field] = "synthetic forbidden value"
                write_sealed(path, payload)
                with self.assertRaises(ValueError):
                    registration.validate_registration(output_root=root, **INPUTS)

    def test_registration_is_write_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "output"
            first = registration.write_registration(output_root=root, **INPUTS)
            with self.assertRaisesRegex(ValueError, "write-once"):
                registration.write_registration(output_root=root, **INPUTS)
            self.assertEqual(first, registration.validate_registration(output_root=root, **INPUTS))

    def test_symlink_or_extra_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "output"
            shutil.copytree(FROZEN_OUTPUT, root)
            (root / "extra.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "inventory"):
                registration.validate_registration(output_root=root, **INPUTS)
            (root / "extra.json").unlink()
            target = root / "request-manifest.json"
            saved = Path(tmp) / "saved.json"
            target.rename(saved)
            target.symlink_to(saved)
            with self.assertRaisesRegex(ValueError, "link"):
                registration.validate_registration(output_root=root, **INPUTS)

    def test_missing_gate_cannot_be_turned_into_quote_or_simulation_authority(self):
        frozen = self.bundle["freeze-manifest.json"]
        self.assertFalse(frozen["boundary"]["metadata_quote_executed"])
        self.assertFalse(frozen["boundary"]["timeseries_acquisition_authorized_by_this_registration"])
        self.assertFalse(frozen["boundary"]["accounts_or_fills_simulated"])
        self.assertEqual(frozen["next_gate"]["maximum_metadata_calls_in_future_quote"], 180)
        self.assertTrue(frozen["next_gate"]["download_requires_successful_exact_quote_and_bounded_consumption_record"])


if __name__ == "__main__":
    unittest.main()
