from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
import unittest

import pandas as pd

from momentumbot.research import early_pullback_paired_adapter_v01 as a
from tests.test_sealed_historical_account_scheduler_v01 import empty_program, spec, attach, repin, reseal
from tests.test_sealed_historical_account_terminal_continuation_v01 import run_fixture as parent_replay
from tests.test_sealed_historical_account_state_producer_v01 import record, SECOND

ROOT = Path(__file__).resolve().parents[1]


def pack(frame):
    return {"columns": list(frame.columns), "index": [t.isoformat() for t in frame.index],
            "data": a.json_safe(frame.values.tolist())}


def causal_source(decision=None, ordinal=1):
    decision = deepcopy(decision or spec()["entry_input"]["source_decision"])
    at = pd.Timestamp(decision["decision_at"])
    qualified = at.floor("10s") - pd.Timedelta(seconds=60)
    activation = {"activation_id": decision["activation_id"], "symbol": decision["symbol"],
        "candidate_qualified_at": qualified.isoformat(), "scanner_record_content_sha256": "c" * 64,
        "eligible_strategy_profile_ids": decision["eligible_strategy_profile_ids"]}
    prices, clocks, sizes = [], [], []
    for i in range(6):
        impulse = i == 0 or (i == 2 and ordinal >= 2) or (i == 4 and ordinal >= 3)
        high = 10.1 + i * .05 if impulse else 9.98
        low = 7.0 if i == 0 else 9.0
        row = (low + .2 if impulse else 9.7, high, low, high - .01 if impulse else 9.5)
        for second, price in zip((1, 2, 4, 6), row):
            clocks.append(qualified + pd.Timedelta(seconds=i * 10 + second))
            prices.append(price)
            sizes.append(250 if impulse else 25)
    clocks.append(at)
    prices.append(10.0)
    sizes.append(100)
    trades = pd.DataFrame({"price": prices, "size": sizes,
        "conditions": [["@"] for _ in clocks], "tape": ["C"] * len(clocks)}, index=pd.DatetimeIndex(clocks))
    minute_index = pd.date_range(qualified.floor("1min") - pd.Timedelta(minutes=20), periods=20, freq="1min")
    minutes = pd.DataFrame({"open": 8.0, "high": 8.1, "low": 7.9, "close": 8.0, "volume": 100}, index=minute_index)
    warmup = minutes.iloc[:10].copy()
    warmup.index = warmup.index - pd.Timedelta(days=1)
    bars = a.micro_bars.aggregate_trade_bars(trades)
    bars = bars.loc[bars.index < at.floor("10s")]
    support = a.indicators.completed_bar_support_series(minutes, ema_warmup=warmup)
    outputs = a.daily.build_micro_trigger_decisions(a.daily.ProfileActivation(**activation),
        bars=bars, trades=trades, support=support, replay_end=at.tz_convert("America/New_York").normalize() + pd.Timedelta(hours=10))
    matches = [r for r in outputs if r.plan["source_bar_start"] == bars.index[-1].isoformat()]
    if len(matches) != 1:
        raise ValueError("synthetic final plan did not form")
    return {"activation": activation, "decision": a.json_safe(asdict(matches[0])),
            "trades": pack(trades), "session_minutes": pack(minutes), "ema_warmup": pack(warmup)}


def authenticate(source):
    return a.authenticate_trigger(source, expected_source_sha256=a.fingerprint(source),
        expected_decision_sha256=a.fingerprint(source["decision"]),
        expected_activation_sha256=a.fingerprint(source["activation"]))


def append_case(program, sources, index=0, ordinal=1, tag="A", **kwargs):
    position = spec(tag, day=program["slots"][index]["trading_date"],
                    scenario=program["slots"][index]["execution_scenario_id"],
                    account=program["slots"][index]["account_key"], **kwargs)
    source = causal_source(position["entry_input"]["source_decision"], ordinal)
    position["entry_input"]["source_decision"] = source["decision"]
    repin(position)
    oid = position["entry_input"]["window"]["opportunity"]["opportunity_id"]
    sources[oid] = {"source": source, "source_sha256": a.fingerprint(source),
                    "activation_sha256": a.fingerprint(source["activation"])}
    program = attach(program, index, position)
    return program, sources


def run(program, sources):
    return a.replay_synthetic_pair(program, sources, expected_program_sha256=a.fingerprint(program),
                                   expected_sources_sha256=a.fingerprint(sources))


def states(result, arm):
    return [r["close"]["account_state"] for r in result["arms"][arm]["sessions"]]


def dispositions(result, arm, index=0):
    return result["arms"][arm]["sessions"][index]["runtime"]["opportunity_dispositions"]


class TriggerBindingTests(unittest.TestCase):
    def test_original_plans_prefixes_and_ordinals_reproduce(self):
        for ordinal in (1, 2, 3):
            with self.subTest(ordinal=ordinal):
                source = causal_source(ordinal=ordinal)
                result = authenticate(source)
                self.assertEqual(result["selection"]["pullback_number"], ordinal)
                self.assertEqual(result["selection"]["selected"], ordinal <= 2)
                self.assertEqual(result["original_micro_prefix_sha256"], source["decision"]["micro_runtime_content_sha256"])
                self.assertFalse(result["raw_provider_archive_authenticated"])
                self.assertFalse(result["scanner_cross_section_authenticated"])

    def test_independent_source_and_decision_pins_required(self):
        source = causal_source()
        kwargs = {"expected_source_sha256": a.fingerprint(source),
                  "expected_decision_sha256": a.fingerprint(source["decision"]),
                  "expected_activation_sha256": a.fingerprint(source["activation"])}
        for key in kwargs:
            with self.subTest(key=key), self.assertRaises(ValueError):
                a.authenticate_trigger(source, **{**kwargs, key: "0" * 64})

    def test_forged_plan_or_prefix_rejected_even_with_rehashed_source(self):
        for field in ("stop_price", "pullback_number", "minimum_new_high_price"):
            source = causal_source()
            source["decision"]["plan"][field] += 1
            source["decision"]["plan_id"] = "plan-" + a.fingerprint({"activation_id": source["decision"]["activation_id"], "plan": source["decision"]["plan"]})
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "does not reproduce"):
                authenticate(source)
        source = causal_source()
        source["decision"]["micro_runtime_content_sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "does not reproduce"):
            authenticate(source)

    def test_earlier_crossing_cannot_be_hidden_by_later_decision(self):
        source = causal_source()
        old = pd.Timestamp(source["decision"]["decision_at"])
        source["decision"]["decision_at"] = (old + pd.Timedelta(seconds=1)).isoformat()
        source["trades"]["index"].append(source["decision"]["decision_at"])
        source["trades"]["data"].append(deepcopy(source["trades"]["data"][-1]))
        with self.assertRaisesRegex(ValueError, "does not reproduce"):
            authenticate(source)

    def test_future_trade_or_uncompleted_minute_rejected(self):
        source = causal_source()
        source["trades"]["index"][-1] = (pd.Timestamp(source["decision"]["decision_at"]) + pd.Timedelta(nanoseconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "trade prefix"):
            authenticate(source)
        source = causal_source()
        source["session_minutes"]["index"][-1] = source["decision"]["candidate_qualified_at"]
        with self.assertRaisesRegex(ValueError, "completed same-session"):
            authenticate(source)

    def test_same_timestamp_trade_order_binds_original_prefix(self):
        source = causal_source()
        source["trades"]["index"].append(source["trades"]["index"][-1])
        source["trades"]["data"].append([10.0, 101, ["@"], "C"])
        with self.assertRaisesRegex(ValueError, "does not reproduce"):
            authenticate(source)

    def test_source_normalization_change_breaks_original_prefix(self):
        source = causal_source()
        source["session_minutes"]["data"][0][0] += .1
        # The original support uses HLC3, so change its close as well.
        source["session_minutes"]["data"][0][3] += .1
        with self.assertRaisesRegex(ValueError, "does not reproduce"):
            authenticate(source)

    def test_wrong_activation_or_profiles_rejected(self):
        for key, value in (("symbol", "SYNTHETICOTHER"), ("eligible_strategy_profile_ids", [])):
            source = causal_source()
            source["activation"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                authenticate(source)

    def test_labels_and_extra_market_columns_rejected(self):
        source = causal_source()
        source["ross_action"] = "buy"
        with self.assertRaises(ValueError):
            authenticate(source)
        for key in ("trades", "session_minutes", "ema_warmup"):
            source = causal_source()
            source[key]["columns"].append("pnl")
            for row in source[key]["data"]:
                row.append(1)
            with self.subTest(key=key), self.assertRaises(ValueError):
                authenticate(source)

    def test_prior_session_warmup_and_clock_order_enforced(self):
        source = causal_source()
        source["ema_warmup"]["index"][-1] = source["decision"]["candidate_qualified_at"]
        with self.assertRaises(ValueError):
            authenticate(source)
        source = causal_source()
        source["trades"]["index"][0], source["trades"]["index"][1] = source["trades"]["index"][1], source["trades"]["index"][0]
        with self.assertRaises(ValueError):
            authenticate(source)


class PairedMechanicsTests(unittest.TestCase):
    def test_all_allowed_control_and_child_preserve_parent_account_state_and_events(self):
        program, sources = append_case(empty_program(count=2), {})
        old = parent_replay(program)[1]
        result = run(program, sources)
        for arm in a.ARMS:
            for i, session in enumerate(result["arms"][arm]["sessions"]):
                self.assertEqual(session["close"]["account_state"], old["sessions"][i]["close"]["account_state"])
                self.assertEqual(session["runtime"]["events"], old["sessions"][i]["runtime"]["events"])
                self.assertEqual(session["runtime"]["processed_streams"], old["sessions"][i]["runtime"]["processed_streams"])

    def test_late_withhold_creates_no_order_campaign_fee_or_position(self):
        program, sources = append_case(empty_program(count=2), {}, ordinal=3)
        result = run(program, sources)
        child = states(result, a.ARMS[1])
        self.assertEqual(dispositions(result, a.ARMS[1])[0]["disposition"], "withheld_late_pullback")
        self.assertEqual(child[-1]["equity_usd"], "30000.00")
        self.assertEqual(child[-1]["campaigns"], [])
        self.assertEqual(child[-1]["cumulative_fees_usd"], "0.00")
        self.assertNotEqual(states(result, a.ARMS[0])[-1]["equity_usd"], child[-1]["equity_usd"])

    def test_withholding_releases_capacity_for_other_symbol_in_same_session(self):
        program, sources = append_case(empty_program(count=1), {}, ordinal=3, tag="A")
        program, sources = append_case(program, sources, ordinal=1, tag="B", offset=SECOND)
        result = run(program, sources)
        self.assertEqual([d["disposition"] for d in dispositions(result, a.ARMS[0])], ["entry_submitted", "blocked_capacity"])
        self.assertEqual([d["disposition"] for d in dispositions(result, a.ARMS[1])], ["withheld_late_pullback", "entry_submitted"])

    def test_each_arm_carries_own_cash_and_own_previous_close(self):
        program, sources = append_case(empty_program(count=2), {}, ordinal=3)
        program, sources = append_case(program, sources, index=1, ordinal=1, tag="B")
        result = run(program, sources)
        closes = []
        for arm in a.ARMS:
            history = result["arms"][arm]["sessions"]
            self.assertEqual(history[1]["runtime"]["opening_account_state_sha256"], a.fingerprint(history[0]["close"]["account_state"]))
            self.assertEqual(history[1]["close"]["previous_close_content_sha256"], history[0]["close"]["content_sha256"])
            self.assertEqual(result["arms"][arm]["seed_application_count"], 1)
            self.assertFalse(history[1]["close"]["seed_applied"])
            closes.append(history[1]["close"]["account_state"]["equity_usd"])
        self.assertNotEqual(*closes)

    def test_open_position_and_blocked_carry_are_independent_between_arms(self):
        program, sources = append_case(empty_program(count=2), {}, ordinal=3, target_fill=2, final_fill=3)
        result = run(program, sources)
        control = result["arms"][a.ARMS[0]]["sessions"]
        child = result["arms"][a.ARMS[1]]["sessions"]
        self.assertTrue(control[0]["close"]["account_state"]["positions"])
        self.assertEqual(control[1]["runtime"]["status"], "blocked_prior_state")
        self.assertEqual(control[1]["close"]["account_state"]["positions"], control[0]["close"]["account_state"]["positions"])
        self.assertEqual(child[1]["runtime"]["status"], "flat_complete")
        self.assertEqual(child[1]["close"]["account_state"]["equity_usd"], "30000.00")

    def test_both_accounts_and_execution_scenarios_preserve_parent_fills_and_fees(self):
        for account in ("main_account", "small_account"):
            for scenario in a.terminal.feedback.SCENARIOS:
                with self.subTest(account=account, scenario=scenario):
                    program, sources = append_case(empty_program(account=account, scenario=scenario, count=1), {})
                    result = run(program, sources)
                    parent = parent_replay(program)[1]["sessions"][0]
                    for arm in a.ARMS:
                        current = result["arms"][arm]["sessions"][0]
                        self.assertEqual(current["runtime"]["reconciliation_snapshot"], parent["runtime"]["reconciliation_snapshot"])
                        self.assertEqual(current["close"]["account_state"], parent["close"]["account_state"])

    def test_trailing_stream_error_is_not_erased_for_withheld_opportunity(self):
        program, sources = append_case(empty_program(count=2), {}, ordinal=3)
        position = program["sessions"][0]["opportunities"][0]["position"]
        position["expected_streams"]["sip_transactions"]["sha256"] = "0" * 64
        program = reseal(program)
        result = run(program, sources)
        self.assertEqual(result["arms"][a.ARMS[1]]["sessions"][0]["runtime"]["status"], "input_failure")
        self.assertEqual(result["arms"][a.ARMS[1]]["sessions"][1]["runtime"]["status"], "blocked_prior_state")
        self.assertEqual(states(result, a.ARMS[1])[0]["equity_usd"], "30000.00")

    def test_missing_and_extra_source_cannot_be_a_withhold(self):
        program, sources = append_case(empty_program(count=1), {})
        for bad in ({}, {**sources, "extra": next(iter(sources.values()))}):
            with self.subTest(keys=list(bad)), self.assertRaises(ValueError):
                run(program, bad)
        program["sessions"][0]["opportunities"] = []
        with self.assertRaises(ValueError):
            run(reseal(program), sources)

    def test_unavailable_reference_retained_and_not_strategy_withheld(self):
        program = empty_program(count=2)
        program["slots"][0]["opportunity_inputs"] = [{"opportunity_id": "missing", "availability_content_sha256": "e" * 64,
            "input_status": "unavailable", "reason": "source_unavailable"}]
        program["slots"][0]["source_date_has_no_micro_decisions"] = False
        program["slots"][0]["unavailable_opportunity_count"] = 1
        program["slots"][0] = reseal(program["slots"][0])
        result = run(reseal(program), {})
        for arm in a.ARMS:
            self.assertEqual(dispositions(result, arm)[0]["disposition"], "unavailable_input")
            self.assertTrue(states(result, arm)[-1]["unresolved_inputs"])
            self.assertFalse(result["arms"][arm]["financial_evaluation_enabled"])

    def test_all_twelve_original_fixture_paths_have_independent_thirty_session_arms(self):
        records = 0
        for account in ("main_account", "small_account"):
            for horizon in (1, 5, 10):
                for scenario in a.terminal.feedback.SCENARIOS:
                    result = run(empty_program(account=account, horizon=horizon, scenario=scenario), {})
                    for arm in a.ARMS:
                        records += len(result["arms"][arm]["sessions"])
                        self.assertEqual(states(result, arm)[-1]["equity_usd"], "30000.00" if account == "main_account" else "2000.00")
        self.assertEqual(records, 720)

    def test_changed_new_catalogue_and_non_synthetic_mode_fail_closed(self):
        program = empty_program(count=1)
        program["slots"][0]["trading_date"] = "2026-03-04"
        program["slots"][0] = reseal(program["slots"][0])
        with self.assertRaises(ValueError):
            run(reseal(program), {})
        program = empty_program(count=1)
        program["input_scope"] = "authenticated_original_historical_sources"
        with self.assertRaises(ValueError):
            run(reseal(program), {})

    def test_input_immutability_and_recomputed_result_rejects_cash_tampering(self):
        program, sources = append_case(empty_program(count=1), {})
        before = deepcopy((program, sources))
        result = run(program, sources)
        self.assertEqual((program, sources), before)
        a.verify_pair(program, sources, result, expected_program_sha256=a.fingerprint(program),
            expected_sources_sha256=a.fingerprint(sources), expected_result_sha256=a.fingerprint(result))
        result["arms"][a.ARMS[1]]["sessions"][0]["close"]["account_state"]["equity_usd"] = "99999.00"
        with self.assertRaisesRegex(ValueError, "does not reproduce"):
            a.verify_pair(program, sources, result, expected_program_sha256=a.fingerprint(program),
                expected_sources_sha256=a.fingerprint(sources), expected_result_sha256=a.fingerprint(result))


class RegistrationTests(unittest.TestCase):
    def test_frozen_registration_and_original_selection_unchanged(self):
        value = a.validate_registration(ROOT)
        self.assertEqual(value["parent_selection_sha256"], a.SELECTION_SHA)
        self.assertFalse(value["discretionary_strategy_integrated"])
        self.assertFalse(value["new_panel_historical_execution_enabled"])

    def test_bounded_plan_has_exact_fixed_dates_four_unarmed_calls_no_cost_guess(self):
        parent = a.selection.validate_registration(ROOT)
        plan = a.build_data_plan(parent)
        self.assertEqual(plan["selected_dates"], parent["sampling"]["selected_dates"])
        self.assertEqual(len(plan["planned_probe_requests"]), 4)
        self.assertEqual(plan["authorized_calls_now"], 0)
        self.assertFalse(plan["automatic_retry_or_pagination"])
        self.assertIsNone(plan["bulk_cost_usd"])
        self.assertFalse(plan["actual_incremental_cost_known"])
        self.assertFalse(plan["new_catalogue_adapter_implemented"])


if __name__ == "__main__":
    unittest.main()
