from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from momentumbot.research.account_chronological_integration import (
    MICRO_POLICY_FINGERPRINT,
    PANEL_ID,
    REGISTERED_DATES,
)
from momentumbot.research.execution_realism import (
    CONTRACT_CONTENT_SHA256 as EXECUTION_CONTRACT_CONTENT_SHA256,
)
from momentumbot.research.prospective_account_evaluation import (
    ACCOUNT_INTEGRATION_CONTENT_SHA256,
    ACCOUNT_KEYS,
    CONTRACT_CONTENT_SHA256,
    EXECUTION_SCENARIOS,
    build_prospective_account_evaluation,
    canonical_fingerprint,
    load_evaluation_contract,
    registered_cells,
    validate_evaluation_contract,
    validate_evaluation_report,
    validate_runtime_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "research" / "strategy" / "prospective-account-evaluation-v0.1.json"
)
AUDIT = (
    ROOT
    / "research"
    / "data-audits"
    / "prospective-account-evaluation-v0.1-registration-2026-08-22.json"
)
SCRIPT = ROOT / "scripts" / "evaluate_prospective_account_panel.py"
RUNTIME_FROZEN_AT = "2026-09-05T12:00:00+00:00"
LABELS_OPENED_AT = "2026-09-05T13:00:00+00:00"


def _rehash(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = canonical_fingerprint(result)
    return result


def _session_hash(
    horizon: int,
    scenario: str,
    trading_date: str,
    account: str,
) -> str:
    value = f"{horizon}|{scenario}|{trading_date}|{account}".encode()
    return hashlib.sha256(value).hexdigest()


def _runtime_decision(
    *,
    horizon: int,
    scenario: str,
    symbol: str,
    account: str,
) -> dict[str, object]:
    common: dict[str, object] = {
        "trading_date": REGISTERED_DATES[0],
        "symbol": symbol,
        "account": account,
        "behavioral_horizon_seconds": horizon,
        "execution_scenario_id": scenario,
        "runtime_content_sha256": _session_hash(
            horizon,
            scenario,
            REGISTERED_DATES[0],
            account,
        ),
        "account_qualified": True,
        "plan_count": 1,
    }
    if symbol == "TEST" and account == "small_account":
        return {
            **common,
            "entry_status": "not_filled",
            "first_entry_at": None,
            "first_entry_price": None,
            "first_entry_pullback_ordinal": None,
            "exit_status": "not_applicable",
            "first_exit_at": None,
            "first_exit_price": None,
            "exit_reason": None,
        }
    entry_price = 10.0 if symbol == "TEST" else 8.0
    return {
        **common,
        "entry_status": "filled",
        "first_entry_at": "2026-08-24T13:00:10+00:00",
        "first_entry_price": entry_price,
        "first_entry_pullback_ordinal": 2,
        "exit_status": "closed",
        "first_exit_at": "2026-08-24T13:01:00+00:00",
        "first_exit_price": entry_price + 0.5,
        "exit_reason": "first_red_1m",
    }


def _runtime_bundle() -> dict[str, object]:
    sessions: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    for horizon, scenario in registered_cells():
        for trading_date in REGISTERED_DATES:
            for account in ACCOUNT_KEYS:
                index = REGISTERED_DATES.index(trading_date)
                if account == "main_account":
                    pnls = [100.0, -40.0] if index == 0 else [0.0, 20.0] if index == 1 else []
                    starting_equity = 10_000.0
                    fees = 1.0
                else:
                    pnls = [20.0, -10.0] if index == 0 else []
                    starting_equity = 2_000.0
                    fees = 0.5
                sessions.append(
                    {
                        "trading_date": trading_date,
                        "account": account,
                        "behavioral_horizon_seconds": horizon,
                        "execution_scenario_id": scenario,
                        "runtime_content_sha256": _session_hash(
                            horizon,
                            scenario,
                            trading_date,
                            account,
                        ),
                        "starting_equity": starting_equity,
                        "runtime_complete": True,
                        "open_position_count": 0,
                        "unavailable_input_count": 0,
                        "closed_campaign_pnls": pnls,
                        "registered_fees": fees,
                    }
                )
        decisions.extend(
            (
                _runtime_decision(
                    horizon=horizon,
                    scenario=scenario,
                    symbol="TEST",
                    account="main_account",
                ),
                _runtime_decision(
                    horizon=horizon,
                    scenario=scenario,
                    symbol="TEST",
                    account="small_account",
                ),
                _runtime_decision(
                    horizon=horizon,
                    scenario=scenario,
                    symbol="UNKN",
                    account="small_account",
                ),
            )
        )
    return _rehash(
        {
            "schema_version": 1,
            "artifact_type": "prospective_account_runtime_evaluation_input",
            "evaluation_contract_content_sha256": CONTRACT_CONTENT_SHA256,
            "panel_id": PANEL_ID,
            "registered_dates": list(REGISTERED_DATES),
            "frozen_parents": {
                "micro_policy_fingerprint": MICRO_POLICY_FINGERPRINT,
                "account_integration_content_sha256": (
                    ACCOUNT_INTEGRATION_CONTENT_SHA256
                ),
                "prospective_execution_content_sha256": (
                    EXECUTION_CONTRACT_CONTENT_SHA256
                ),
            },
            "runtime_frozen_at": RUNTIME_FROZEN_AT,
            "runtime_frozen_before_retrospective_review": True,
            "retrospective_review_started": False,
            "raw_transcript_text_persisted": False,
            "runtime_strategy_effect": "none",
            "decisions": decisions,
            "sessions": sessions,
        }
    )


def _human_decisions() -> list[dict[str, object]]:
    evidence = "e" * 64
    return [
        {
            "trading_date": REGISTERED_DATES[0],
            "symbol": "TEST",
            "account": "main_account",
            "human_state": "participated",
            "trade_completion": "completed_trade",
            "evidence_content_sha256": evidence,
            "reported_entry_times": [
                "2026-08-24T13:00:08+00:00",
                "2026-08-24T13:00:12+00:00",
            ],
            "reported_entry_prices": [9.9, 10.1],
            "reported_entry_pullback_ordinal": 2,
            "reported_exit_times": [
                "2026-08-24T13:00:50+00:00",
                "2026-08-24T13:01:10+00:00",
            ],
            "reported_exit_prices": [10.4, 10.6],
            "reported_exit_reasons": ["first_red_1m", "topping_tail"],
        },
        {
            "trading_date": REGISTERED_DATES[0],
            "symbol": "TEST",
            "account": "small_account",
            "human_state": "explicitly_skipped_or_rejected",
            "trade_completion": "no_trade",
            "evidence_content_sha256": evidence,
            "reported_entry_times": [],
            "reported_entry_prices": [],
            "reported_entry_pullback_ordinal": None,
            "reported_exit_times": [],
            "reported_exit_prices": [],
            "reported_exit_reasons": [],
        },
        {
            "trading_date": REGISTERED_DATES[0],
            "symbol": "UNKN",
            "account": "small_account",
            "human_state": "not_mentioned_or_unobservable",
            "trade_completion": "unknown",
            "evidence_content_sha256": evidence,
            "reported_entry_times": [],
            "reported_entry_prices": [],
            "reported_entry_pullback_ordinal": None,
            "reported_exit_times": [],
            "reported_exit_prices": [],
            "reported_exit_reasons": [],
        },
        {
            "trading_date": REGISTERED_DATES[0],
            "symbol": "MISS",
            "account": "main_account",
            "human_state": "participated",
            "trade_completion": "completed_trade",
            "evidence_content_sha256": evidence,
            "reported_entry_times": [],
            "reported_entry_prices": [],
            "reported_entry_pullback_ordinal": None,
            "reported_exit_times": [],
            "reported_exit_prices": [],
            "reported_exit_reasons": [],
        },
        {
            "trading_date": REGISTERED_DATES[0],
            "symbol": "MAYBE",
            "account": "main_account",
            "human_state": "discussed_but_action_unclear",
            "trade_completion": "attempted_no_fill",
            "evidence_content_sha256": evidence,
            "reported_entry_times": [],
            "reported_entry_prices": [],
            "reported_entry_pullback_ordinal": None,
            "reported_exit_times": [],
            "reported_exit_prices": [],
            "reported_exit_reasons": [],
        },
        {
            "trading_date": REGISTERED_DATES[0],
            "symbol": "UNAV",
            "account": "small_account",
            "human_state": "source_unavailable",
            "trade_completion": "source_unavailable",
            "evidence_content_sha256": evidence,
            "reported_entry_times": [],
            "reported_entry_prices": [],
            "reported_entry_pullback_ordinal": None,
            "reported_exit_times": [],
            "reported_exit_prices": [],
            "reported_exit_reasons": [],
        },
    ]


def _labels_bundle(
    contract: dict[str, object],
    runtime: dict[str, object],
) -> dict[str, object]:
    return _rehash(
        {
            "schema_version": 1,
            "artifact_type": "prospective_account_retrospective_labels",
            "evaluation_contract_content_sha256": CONTRACT_CONTENT_SHA256,
            "panel_id": PANEL_ID,
            "registered_dates": list(REGISTERED_DATES),
            "runtime_content_sha256": runtime["content_sha256"],
            "runtime_frozen_at": RUNTIME_FROZEN_AT,
            "labels_opened_at": LABELS_OPENED_AT,
            "labels_opened_after_runtime_hash_freeze": True,
            "label_policy": copy.deepcopy(contract["label_policy"]),
            "raw_transcript_text_persisted": False,
            "runtime_strategy_effect": "none",
            "decisions": _human_decisions(),
        }
    )


def _rebind_labels(
    labels: dict[str, object],
    runtime: dict[str, object],
) -> dict[str, object]:
    changed = copy.deepcopy(labels)
    changed["runtime_content_sha256"] = runtime["content_sha256"]
    return _rehash(changed)


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(key)
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


class ProspectiveAccountEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_evaluation_contract(CONTRACT)
        cls.runtime = _runtime_bundle()
        cls.labels = _labels_bundle(cls.contract, cls.runtime)
        cls.report = build_prospective_account_evaluation(
            contract=cls.contract,
            runtime_bundle=cls.runtime,
            labels_bundle=cls.labels,
        )

    def test_contract_binds_parents_cells_metrics_and_no_authority(self):
        self.assertEqual(self.contract["content_sha256"], CONTRACT_CONTENT_SHA256)
        self.assertEqual(len(self.contract["equal_report_cells"]), 6)
        self.assertEqual(
            self.contract["frozen_parents"]["micro_policy_fingerprint"],
            MICRO_POLICY_FINGERPRINT,
        )
        self.assertEqual(
            self.contract["frozen_parents"][
                "prospective_execution_content_sha256"
            ],
            EXECUTION_CONTRACT_CONTENT_SHA256,
        )
        limits = self.contract["metric_registry"]["aggregation_limits"]
        self.assertTrue(limits["cells_reported_separately"])
        self.assertFalse(limits["best_cell_selection_allowed"])
        self.assertFalse(limits["weighted_overall_imitation_score_allowed"])
        self.assertEqual(
            self.contract["authority_boundary"]["runtime_strategy_effect"],
            "none",
        )
        self.assertFalse(
            self.contract["authority_boundary"]["provider_call_authorized"]
        )

    def test_rehashed_contract_scope_expansion_is_rejected(self):
        changed = copy.deepcopy(self.contract)
        changed["authority_boundary"]["best_cell_selection_authorized"] = True
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "content hash mismatch"):
            validate_evaluation_contract(changed)

    def test_account_scoped_component_metrics_keep_unknowns_out(self):
        cell = self.report["component_metrics"][
            "h1s::l1-conservative-v0.1"
        ]
        main = cell["main_account"]
        self.assertEqual(main["observed_completed_trade_count"], 2)
        self.assertEqual(main["acquisition_evaluable_completed_trade_count"], 2)
        self.assertEqual(main["acquired_completed_trade_count"], 1)
        self.assertEqual(main["descriptive_acquisition_fraction"], 0.5)
        self.assertEqual(main["bot_fill_on_human_trade_count"], 1)
        self.assertEqual(main["descriptive_trade_skip_agreement_fraction"], 0.5)

        small = cell["small_account"]
        self.assertEqual(small["explicit_skip_count"], 1)
        self.assertEqual(small["bot_fill_on_explicit_skip_count"], 0)
        self.assertEqual(small["evaluable_trade_skip_decision_count"], 1)
        self.assertEqual(small["descriptive_trade_skip_agreement_fraction"], 1.0)
        self.assertEqual(
            small["relation_counts"]["excluded_not_mentioned_or_unobservable"],
            1,
        )

    def test_all_reported_entry_and_exit_references_are_retained(self):
        row = next(
            row
            for row in self.report["decision_comparisons"]
            if row["cell_id"] == "h1s::l1-conservative-v0.1"
            and row["symbol"] == "TEST"
            and row["account"] == "main_account"
        )
        entry = row["entry_alignment"]
        self.assertEqual(entry["all_time_deltas_seconds"], [2.0, -2.0])
        self.assertEqual(len(entry["all_price_differences"]), 2)
        self.assertFalse(entry["nearest_reference_selected"])
        self.assertTrue(entry["pullback_ordinal_match"])
        exit_alignment = row["exit_alignment"]
        self.assertEqual(exit_alignment["all_time_deltas_seconds"], [10.0, -10.0])
        self.assertEqual(exit_alignment["exact_reason_matches"], [True, False])
        self.assertFalse(exit_alignment["nearest_reference_selected"])

    def test_complete_flat_portfolio_metrics_are_deterministic(self):
        main = self.report["portfolio_metrics"][
            "h1s::l1-conservative-v0.1"
        ]["main_account"]
        self.assertTrue(main["portfolio_metrics_eligible"])
        self.assertEqual(main["gross_realized_pnl"], 80.0)
        self.assertEqual(main["registered_fees"], 10.0)
        self.assertEqual(main["net_pnl_after_registered_fees"], 70.0)
        self.assertEqual(main["net_return_fraction"], 0.007)
        self.assertEqual(main["closed_campaign_count"], 4)
        self.assertEqual(main["closed_campaign_win_rate"], 0.5)
        self.assertEqual(main["gross_expectancy_per_closed_campaign"], 20.0)
        self.assertEqual(main["gross_profit_factor"], 3.0)
        self.assertEqual(main["gross_max_realized_drawdown"], 40.0)

    def test_any_open_or_unavailable_session_nulls_only_its_account_cell(self):
        mutations = (
            ("open_position_count", 1),
            ("unavailable_input_count", 1),
            ("runtime_complete", False),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                runtime = copy.deepcopy(self.runtime)
                session = next(
                    row
                    for row in runtime["sessions"]
                    if row["behavioral_horizon_seconds"] == 1
                    and row["execution_scenario_id"] == EXECUTION_SCENARIOS[0]
                    and row["trading_date"] == REGISTERED_DATES[0]
                    and row["account"] == "main_account"
                )
                session[field] = value
                runtime = _rehash(runtime)
                labels = _rebind_labels(self.labels, runtime)
                report = build_prospective_account_evaluation(
                    contract=self.contract,
                    runtime_bundle=runtime,
                    labels_bundle=labels,
                )
                blocked = report["portfolio_metrics"][
                    "h1s::l1-conservative-v0.1"
                ]["main_account"]
                self.assertFalse(blocked["portfolio_metrics_eligible"])
                for financial in (
                    "gross_realized_pnl",
                    "registered_fees",
                    "net_pnl_after_registered_fees",
                    "net_return_fraction",
                    "closed_campaign_win_rate",
                    "gross_expectancy_per_closed_campaign",
                    "gross_profit_factor",
                    "gross_max_realized_drawdown",
                ):
                    self.assertIsNone(blocked[financial])
                unaffected = report["portfolio_metrics"][
                    "h1s::l1-conservative-v0.1"
                ]["small_account"]
                self.assertTrue(unaffected["portfolio_metrics_eligible"])
                if field == "runtime_complete":
                    components = report["component_metrics"][
                        "h1s::l1-conservative-v0.1"
                    ]["main_account"]
                    self.assertEqual(
                        components["acquisition_evaluable_completed_trade_count"],
                        0,
                    )
                    self.assertIsNone(
                        components["descriptive_acquisition_fraction"]
                    )
                    self.assertEqual(
                        components["evaluable_trade_skip_decision_count"],
                        0,
                    )
                    self.assertIsNone(
                        components["descriptive_trade_skip_agreement_fraction"]
                    )

    def test_candidate_set_and_session_hash_mismatches_fail_closed(self):
        changed = copy.deepcopy(self.runtime)
        changed["decisions"].pop(0)
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "identical candidate set"):
            validate_runtime_bundle(changed)

        changed = copy.deepcopy(self.runtime)
        changed["decisions"][0]["runtime_content_sha256"] = "d" * 64
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "bind its account session"):
            validate_runtime_bundle(changed)

    def test_runtime_rejects_retrospective_keys_even_when_rehashed(self):
        changed = copy.deepcopy(self.runtime)
        changed["ross_action"] = "participated"
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "retrospective label keys"):
            validate_runtime_bundle(changed)

    def test_labels_must_be_opened_after_exact_runtime_freeze(self):
        changed = copy.deepcopy(self.labels)
        changed["labels_opened_at"] = RUNTIME_FROZEN_AT
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "opened after runtime freeze"):
            build_prospective_account_evaluation(
                contract=self.contract,
                runtime_bundle=self.runtime,
                labels_bundle=changed,
            )

        changed = copy.deepcopy(self.labels)
        changed["runtime_frozen_at"] = "2026-09-05T11:59:59+00:00"
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "freeze timestamp changed"):
            build_prospective_account_evaluation(
                contract=self.contract,
                runtime_bundle=self.runtime,
                labels_bundle=changed,
            )

    def test_report_has_no_best_cell_or_overall_imitation_score(self):
        keys = _walk_keys(self.report)
        self.assertNotIn("best_cell", keys)
        self.assertNotIn("selected_horizon", keys)
        self.assertNotIn("overall_imitation_score", keys)
        self.assertNotIn("aggregate_imitation_score", keys)
        self.assertFalse(
            self.report["authority_boundary"]["best_cell_selection_allowed"]
        )
        self.assertFalse(
            self.report["authority_boundary"][
                "weighted_overall_imitation_score_allowed"
            ]
        )

    def test_rehashed_report_tampering_is_recomputed_and_rejected(self):
        changed = copy.deepcopy(self.report)
        changed["component_metrics"]["h1s::l1-conservative-v0.1"][
            "main_account"
        ]["bot_fill_on_human_trade_count"] = 99
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "component metrics"):
            validate_evaluation_report(changed)

        changed = copy.deepcopy(self.report)
        aligned = next(
            row
            for row in changed["decision_comparisons"]
            if row["entry_alignment"] is not None
        )
        aligned["entry_alignment"] = None
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "entry alignment"):
            validate_evaluation_report(changed)

        changed = copy.deepcopy(self.report)
        changed["decision_comparisons"].pop()
        changed = _rehash(changed)
        with self.assertRaisesRegex(ValueError, "label set differs"):
            validate_evaluation_report(changed)

    def test_report_validator_accepts_builder_output(self):
        validate_evaluation_report(self.report)
        self.assertTrue(
            self.report["candidate_identity"][
                "identical_candidate_set_across_all_cells"
            ]
        )

    def test_cli_writes_once_and_validates_before_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "runtime.json"
            labels = root / "labels.json"
            output = root / "report.json"
            runtime.write_text(json.dumps(self.runtime), encoding="utf-8")
            labels.write_text(json.dumps(self.labels), encoding="utf-8")
            command = [
                sys.executable,
                str(SCRIPT),
                "--runtime",
                str(runtime),
                "--labels",
                str(labels),
                "--output",
                str(output),
            ]
            environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
            first = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            validate_evaluation_report(json.loads(output.read_text(encoding="utf-8")))
            second = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("FileExistsError", second.stderr)

    def test_registration_audit_is_hash_bound_and_inert(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        unsigned = {key: value for key, value in audit.items() if key != "content_sha256"}
        self.assertEqual(canonical_fingerprint(unsigned), audit["content_sha256"])
        self.assertEqual(audit["contract"]["content_sha256"], CONTRACT_CONTENT_SHA256)
        for row in audit["bound_files"]:
            self.assertEqual(
                hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(),
                row["file_sha256"],
            )
        authority = audit["authority_boundary"]
        self.assertFalse(authority["retrospective_labels_loaded"])
        self.assertFalse(authority["later_prices_or_pnl_loaded"])
        self.assertFalse(authority["provider_call_run"])
        self.assertFalse(authority["broker_order_submitted"])
        self.assertFalse(authority["runtime_authority_created"])


if __name__ == "__main__":
    unittest.main()
