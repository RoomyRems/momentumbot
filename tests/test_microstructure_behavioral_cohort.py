import copy
import hashlib
import json
import unittest
from pathlib import Path

from momentumbot.research.databento_behavioral_cohort_execution_v01 import (
    load_execution_authorization,
)
from momentumbot.research.microstructure_behavioral_cohort import (
    COHORT_CONTENT_SHA256,
    EXPECTED_OPPORTUNITY_COUNT,
    EXPECTED_QUANTITY_TOTAL,
    EXPECTED_REQUEST_COUNT,
    cohort_request_for_opportunity,
    load_and_validate_behavioral_cohort,
    timestamp_ns,
    validate_behavioral_cohort,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "research" / "strategy" / "microstructure-behavioral-cohort-v0.1.json"
)
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "microstructure-behavioral-cohort-v0.1-registration-2026-08-21.json"
)
EXECUTION_AUTHORIZATION = (
    ROOT / "research/strategy/microstructure-behavioral-cohort-v0.1-execution.json"
)
EXECUTION_WORKFLOW = (
    ROOT
    / ".github/workflows/databento-microstructure-behavioral-cohort-v01.yml"
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MicrostructureBehavioralCohortTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_and_validate_behavioral_cohort(CONTRACT)

    def test_contract_is_hash_bound_and_unarmed(self):
        self.assertEqual(self.contract["content_sha256"], COHORT_CONTENT_SHA256)
        self.assertFalse(self.contract["provider_request_authorized"])
        self.assertFalse(self.contract["provider_purchase_authorized"])
        self.assertFalse(self.contract["execution_file_present"])
        gate = self.contract["future_execution_gate"]
        self.assertEqual(gate["exact_request_count_authorized_now"], 0)
        self.assertEqual(gate["provider_cost_authorized_now_usd"], "0")
        self.assertEqual(gate["provider_bytes_authorized_now"], 0)

    def test_exhaustive_panel_slice_and_quantities_are_frozen(self):
        rows = self.contract["opportunities"]
        self.assertEqual(len(rows), EXPECTED_OPPORTUNITY_COUNT)
        self.assertEqual(
            sum(row["prospective_order_quantity"] for row in rows),
            EXPECTED_QUANTITY_TOTAL,
        )
        self.assertEqual(
            [(row["symbol"], row["prospective_order_quantity"]) for row in rows],
            [
                ("GMM", 577),
                ("PLSM", 220),
                ("VEEE", 197),
                ("VEEE", 300),
                ("NXTC", 536),
                ("NXTC", 833),
                ("SHPH", 625),
                ("BIYA", 681),
                ("BIYA", 340),
                ("NEUP", 1249),
            ],
        )
        self.assertEqual({row["role"] for row in rows}, {"starter", "reentry"})

    def test_requests_group_dates_and_minimize_the_registered_end(self):
        requests = self.contract["request_surface"]["requests"]
        self.assertEqual(len(requests), EXPECTED_REQUEST_COUNT)
        self.assertEqual(
            [request["symbols"] for request in requests],
            [["GMM"], ["PLSM", "VEEE"], ["NXTC", "SHPH"], ["BIYA"], ["NEUP"]],
        )
        for request in requests:
            date_rows = [
                row
                for row in self.contract["opportunities"]
                if row["trading_date"] == request["trading_date"]
            ]
            latest = max(timestamp_ns(row["anchor_receive_time"]) for row in date_rows)
            self.assertEqual(timestamp_ns(request["end"]), latest + 10_000_000_001)

    def test_every_opportunity_maps_to_one_exact_request(self):
        for row in self.contract["opportunities"]:
            request = cohort_request_for_opportunity(
                self.contract, row["opportunity_id"]
            )
            self.assertEqual(request["trading_date"], row["trading_date"])
            self.assertIn(row["symbol"], request["symbols"])
        with self.assertRaises(KeyError):
            cohort_request_for_opportunity(self.contract, "not-registered")

    def test_selection_quantity_request_and_authority_drift_fail_closed(self):
        mutations = []
        changed = copy.deepcopy(self.contract)
        changed["selection_rule"]["uses_retrospective_outcomes"] = True
        mutations.append(changed)
        changed = copy.deepcopy(self.contract)
        changed["opportunities"][0]["prospective_order_quantity"] = 578
        mutations.append(changed)
        changed = copy.deepcopy(self.contract)
        changed["request_surface"]["requests"][0]["end"] = (
            "2026-07-10T11:03:53.796117448Z"
        )
        mutations.append(changed)
        changed = copy.deepcopy(self.contract)
        changed["provider_request_authorized"] = True
        mutations.append(changed)
        for mutation in mutations:
            with self.assertRaises(ValueError):
                validate_behavioral_cohort(mutation)

    def test_execution_gate_is_absent_or_exactly_valid(self):
        if EXECUTION_AUTHORIZATION.exists():
            load_execution_authorization(EXECUTION_AUTHORIZATION)
            self.assertTrue(EXECUTION_WORKFLOW.is_file())
        else:
            self.assertFalse(EXECUTION_AUTHORIZATION.exists())
        self.assertFalse(
            (ROOT / ".github/workflows/microstructure-behavioral-cohort-v0.1.yml").exists()
        )

    def test_registration_audit_binds_the_implementation(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertFalse(audit["provider_request_made"])
        self.assertFalse(audit["databento_credit_used"])
        for bound in audit["bound_files"]:
            self.assertEqual(file_sha256(ROOT / bound["path"]), bound["file_sha256"])
        unsigned = {key: value for key, value in audit.items() if key != "content_sha256"}
        from momentumbot.research.microstructure_contract import canonical_fingerprint

        self.assertEqual(canonical_fingerprint(unsigned), audit["content_sha256"])


if __name__ == "__main__":
    unittest.main()
