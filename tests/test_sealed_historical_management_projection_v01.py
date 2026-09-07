from __future__ import annotations

import copy
import hashlib
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import yaml

from momentumbot import micro_bars
from momentumbot.micro_execution import execution_eligible_trades
from momentumbot.research import execution_realism as execution
from momentumbot.research import prospective_market_input_capture as capture
from momentumbot.research import prospective_management_window as legacy
from momentumbot.research import sealed_historical_management_projection_v01 as m

ROOT = Path(__file__).resolve().parents[1]
BASE = int(pd.Timestamp("2025-05-30T14:00:00Z").value)
SECOND = 1_000_000_000


def window():
    return {"opportunity": {"opportunity_id": "synthetic-opportunity", "symbol": "SYNTHETIC",
        "trading_date": "2025-05-30", "decision_ts_ns": BASE}, "start_ns": BASE,
        "signal_end_ns": BASE + m.SIGNAL_NS, "end_ns": BASE + m.SIGNAL_NS + m.TAIL_NS,
        "entry_input_status": "available", "entry_input_reason": "synthetic_available"}


def trade(offset, price=10.0, conditions=None, tape="C"):
    return {"t": pd.Timestamp(BASE + offset, unit="ns", tz="UTC").isoformat(),
        "p": price, "s": 25, "i": 10, "x": "Q", "z": tape, "c": ["@"] if conditions is None else conditions}


def bar(minute=0, opening=10.0, closing=10.0):
    return {"t": pd.Timestamp(BASE + minute * m.MINUTE_NS, unit="ns", tz="UTC").isoformat(),
        "o": opening, "h": max(opening, closing) + 1, "l": min(opening, closing) - 1,
        "c": closing, "v": 100, "n": 5, "vw": (opening + closing) / 2}


def envelopes(rows, *, resource="sip_transactions", first=42):
    return [{"record": row, "timestamp_ns": int(pd.Timestamp(row["t"]).value),
        "composed_record_ordinal": first + i, "source_artifact_id": 123,
        "source_request_id": "synthetic-" + resource, "source_record_ordinal": 100 + i}
        for i, row in enumerate(rows)]


def project(trades=(), bars=(), **kwargs):
    return m.project_external_fill_proxy(window=kwargs.pop("window", window()),
        fill_time_ns=kwargs.pop("fill_time_ns", BASE + 1), fill_price=kwargs.pop("fill_price", 10.0),
        stop_price=kwargs.pop("stop_price", 9.0), trades=envelopes(trades),
        bars=envelopes(bars, resource="raw_sip_1m_bars"), **kwargs)


class ManagementProjectionTests(unittest.TestCase):
    def test_registration_binds_verified_parent_and_keeps_runtime_closed(self):
        report = m.validate_registration(ROOT)
        self.assertTrue(report["verification_passed"])
        contract = m.expected_contract(ROOT)
        self.assertEqual(contract["parent_commit_sha"], "f4a8d98b5ff780a4138ed4eb5628423891e4818d")
        self.assertEqual(contract["selected_cell_id"], legacy.SELECTED_CELL_ID)
        self.assertIsNone(contract["historical_entry_producer"])
        self.assertFalse(contract["historical_projection_runner_registered"])
        for k, v in m.BOUNDARY.items():
            self.assertEqual(contract[k], v)

    def test_parent_mutation_cannot_be_resealed(self):
        original = m.file_sha
        with patch.object(m, "file_sha", side_effect=lambda p: "0" * 64 if str(p).endswith(m.INPUT_AUDIT) else original(p)):
            with self.assertRaisesRegex(ValueError, "parent differs"):
                m.validate_registration(ROOT)

    def test_implementation_mutation_invalidates_registration(self):
        original = m.file_sha
        with patch.object(m, "file_sha", side_effect=lambda p: "0" * 64 if str(p).endswith(m.MODULE_PATH) else original(p)):
            with self.assertRaisesRegex(ValueError, "registration differs"):
                m.validate_registration(ROOT)

    def test_frozen_signal_tail_and_exit_capture_constants_match(self):
        self.assertEqual(m.SIGNAL_NS, legacy.SIGNAL_WINDOW_NS)
        self.assertEqual(m.TAIL_NS, legacy.EXECUTION_TAIL_NS)
        self.assertEqual(m.MINUTE_NS, legacy.MINUTE_NS)
        self.assertEqual(m.PRE_QUOTE_NS, capture.PRE_DECISION_QUOTE_NS)
        self.assertEqual(m.POST_QUOTE_NS, capture.POST_DECISION_CAPTURE_NS)
        self.assertEqual(m.exit_requirements()["dataset"], capture.DATASET)
        self.assertEqual(m.exit_requirements()["stype_in"], capture.STYPE_IN)

    def test_all_frozen_conditions_and_pairs_match_micro_eligibility(self):
        codes = [*micro_bars._ALWAYS, "B", "UNKNOWN"]
        combinations = [[], *[[c] for c in codes], *[list(pair) for pair in itertools.product(codes, repeat=2)]]
        rows = [trade(2, conditions=conditions, tape=tape) for tape in ("A", "B", "C") for conditions in combinations]
        frame = pd.DataFrame({"price": [r["p"] for r in rows], "conditions": [r["c"] for r in rows],
            "tape": [r["z"] for r in rows]}, index=pd.DatetimeIndex([pd.Timestamp(r["t"]) for r in rows]))
        path = execution_eligible_trades(frame)
        expected = {int(r["_source_sequence"]): bool(r["_execution_via_odd_lot"]) for _, r in path.iterrows()}
        for i, row in enumerate(rows):
            self.assertEqual(m.print_eligibility(row), (i in expected, expected.get(i, False)), (row["z"], row["c"]))

    def test_clean_odd_lot_is_transaction_only(self):
        out = project([trade(2, 8, ["I"])])
        self.assertEqual(out["legs"][0]["reason"], "initial_stop")
        self.assertTrue(out["legs"][0]["execution_via_odd_lot"])
        self.assertFalse(out["executable_fill"])

    def test_zero_size_retains_frozen_price_eligibility_without_new_filter(self):
        row = trade(2, 8)
        row["s"] = 0
        self.assertEqual(project([row])["legs"][0]["reason"], "initial_stop")

    def test_existing_float_target_rounding_is_not_reinterpreted(self):
        fill, stop = 10.0, 9.999999999999
        out = project([trade(2, 10.0)], fill_price=fill, stop_price=stop)
        self.assertEqual(out["first_target_price"], round(fill + 2.0 * (fill - stop), 10))
        self.assertEqual(out["legs"][0]["reason"], "first_target")

    def test_unknown_or_disqualified_odd_lot_cannot_trigger(self):
        for conditions in (["UNKNOWN"], ["I", "UNKNOWN"], ["I", "Z"]):
            with self.subTest(conditions=conditions):
                self.assertEqual(project([trade(2, 8, conditions)])["legs"], [])

    def test_all_same_fill_timestamp_prints_are_excluded(self):
        out = project([trade(1, 8), trade(1, 15), trade(2, 10)])
        self.assertEqual(out["legs"], [])
        self.assertEqual(out["remaining_fraction"], 1.0)

    def test_one_nanosecond_after_fill_can_trigger(self):
        out = project([trade(2, 8)])
        self.assertEqual(out["legs"][0]["exit_time_ns"], BASE + 2)

    def test_equal_timestamp_source_order_preserved(self):
        forward = project([trade(2, 12), trade(2, 10)])
        reverse = project([trade(2, 10), trade(2, 12)])
        self.assertEqual([x["reason"] for x in forward["legs"]], ["first_target", "breakeven_stop"])
        self.assertEqual([x["reason"] for x in reverse["legs"]], ["first_target"])
        self.assertEqual([x["trade_evidence"]["source_record_ordinal"] for x in forward["legs"]], [100, 101])

    def test_red_not_visible_at_bar_start_or_before_close(self):
        out = project([trade(59 * SECOND, 12)], [bar(0, 11, 10)])
        self.assertEqual(out["legs"][0]["reason"], "first_target")
        self.assertEqual(out["remaining_fraction"], 0.5)
        self.assertEqual(out["first_red_signal"]["signal_ts_ns"], BASE + m.MINUTE_NS)

    def test_completed_red_beats_target_at_exact_close(self):
        out = project([trade(m.MINUTE_NS, 12)], [bar(0, 11, 10)])
        leg = out["legs"][0]
        self.assertEqual(leg["reason"], "first_red_candle")
        self.assertEqual(leg["quantity_fraction"], 1.0)
        self.assertEqual(leg["completed_red_signal"]["signal_ts_ns"], BASE + m.MINUTE_NS)
        self.assertEqual(leg["completed_red_signal"]["bar_evidence"]["source_record_ordinal"], 100)

    def test_stop_beats_completed_red(self):
        out = project([trade(m.MINUTE_NS, 8)], [bar(0, 11, 10)])
        self.assertEqual(out["legs"][0]["reason"], "initial_stop")

    def test_breakeven_stop_beats_completed_red(self):
        out = project([trade(2, 12), trade(m.MINUTE_NS, 10)], [bar(0, 11, 10)])
        self.assertEqual([leg["reason"] for leg in out["legs"]], ["first_target", "breakeven_stop"])

    def test_bar_closing_at_fill_is_excluded(self):
        out = project([trade(m.MINUTE_NS + 1, 10)], [bar(0, 11, 10)], fill_time_ns=BASE + m.MINUTE_NS)
        self.assertIsNone(out["first_red_signal"])
        self.assertEqual(out["legs"], [])

    def test_signal_end_is_inclusive_but_next_bar_close_is_excluded(self):
        at_end = project([trade(m.SIGNAL_NS, 11)], [bar(14, 11, 10)])
        after_end = project([trade(m.SIGNAL_NS + 1, 11)], [bar(15, 11, 10)])
        self.assertEqual(at_end["legs"][0]["reason"], "first_red_candle")
        self.assertIsNone(after_end["first_red_signal"])

    def test_stop_and_target_continue_through_original_tail(self):
        out = project([trade(m.SIGNAL_NS + 1, 12), trade(m.SIGNAL_NS + m.TAIL_NS - 1, 10)])
        self.assertEqual([x["reason"] for x in out["legs"]], ["first_target", "breakeven_stop"])

    def test_no_post_terminal_red_metadata(self):
        out = project([trade(2, 8)], [bar(1, 11, 10)])
        self.assertIsNone(out["first_red_signal"])
        self.assertEqual(out["remaining_fraction"], 0)

    def test_pending_red_without_following_eligible_print_stays_open(self):
        out = project([trade(m.MINUTE_NS + 1, 8, ["UNKNOWN"])], [bar(0, 11, 10)])
        self.assertIsNotNone(out["first_red_signal"])
        self.assertEqual(out["status"], "open_proxy")
        self.assertFalse(out["account_position_closed"])

    def test_empty_path_is_not_liquidated(self):
        out = project()
        self.assertEqual(out["legs"], [])
        self.assertEqual(out["remaining_fraction"], 1)
        self.assertEqual(out["active_stop_price"], 9)

    def test_target_gap_retains_target_proxy_and_observed_source_price(self):
        source = trade(2, 13)
        out = project([source])
        leg = out["legs"][0]
        self.assertEqual(leg["proxy_price"], 12)
        self.assertEqual(leg["observed_trade_price"], 13)
        self.assertEqual(leg["trade_evidence"]["record_content_sha256"], hashlib.sha256(m.inputs.reuse._canonical_line(source)).hexdigest())
        self.assertEqual(out["remaining_fraction"], 0.5)
        self.assertEqual(out["active_stop_price"], 10)

    def test_repeated_target_prints_cannot_sell_extra_fraction(self):
        out = project([trade(2, 12), trade(3, 13), trade(4, 14)])
        self.assertEqual(len(out["legs"]), 1)
        self.assertEqual(out["remaining_fraction"], 0.5)

    def test_inputs_not_mutated_and_outputs_detached(self):
        w, trades, bars = window(), envelopes([trade(m.MINUTE_NS, 10)]), envelopes([bar(0, 11, 10)], resource="raw_sip_1m_bars")
        before = copy.deepcopy((w, trades, bars))
        out = m.project_external_fill_proxy(window=w, fill_time_ns=BASE + 1, fill_price=10, stop_price=9, trades=trades, bars=bars)
        self.assertEqual((w, trades, bars), before)
        out["first_red_signal"]["bar_evidence"]["source_record_ordinal"] = 999
        self.assertEqual((w, trades, bars), before)

    def test_unavailable_entry_is_never_repaired_by_management(self):
        w = window()
        w["entry_input_status"] = "unavailable"
        w["entry_input_reason"] = "frozen_reason"
        with self.assertRaisesRegex(ValueError, "unavailable entry"):
            project([trade(2, 12)], window=w)
        with self.assertRaisesRegex(ValueError, "unavailable entry"):
            m.conditional_exit_envelope(w, BASE + 2)
        self.assertEqual(w["entry_input_reason"], "frozen_reason")

    def test_invalid_fill_and_stop_fail_closed(self):
        cases = [{"fill_time_ns": BASE - 1}, {"fill_time_ns": BASE + m.SIGNAL_NS + m.TAIL_NS},
            {"fill_time_ns": float(BASE)}, {"fill_time_ns": True}, {"fill_price": float("nan")},
            {"fill_price": True}, {"fill_price": "10"}, {"stop_price": 0}, {"stop_price": 10},
            {"stop_price": float("inf")}, {"fill_price": 1e308, "stop_price": 1.0}]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                project(**kwargs)

    def test_original_window_required(self):
        for key in ("start_ns", "signal_end_ns", "end_ns"):
            w = window()
            w[key] += 1
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "original opportunity"):
                project(window=w)

    def test_source_window_end_exclusive_and_start_inclusive(self):
        self.assertEqual(project([trade(0, 8), trade(2, 10)])["legs"], [])
        for offset in (-1, m.SIGNAL_NS + m.TAIL_NS):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "outside original"):
                project([trade(offset)])

    def test_unsorted_or_duplicate_bars_fail_closed(self):
        for bars in ([bar(1), bar(0)], [bar(0), bar(0)]):
            with self.assertRaises(ValueError):
                project(bars=bars)

    def test_unsorted_prints_or_noncanonical_rows_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "source order"):
            project([trade(3), trade(2)])
        for field, bad in (("p", float("nan")), ("s", True), ("c", "@"), ("z", "X")):
            row = trade(2)
            row[field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                project([row])

    def test_lineage_and_timestamp_tampering_fail_closed(self):
        for field, bad in (("composed_record_ordinal", 44), ("source_record_ordinal", 105),
                           ("timestamp_ns", BASE + 4), ("source_artifact_id", True)):
            rows = envelopes([trade(2), trade(3)])
            rows[1][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.project_external_fill_proxy(window=window(), fill_time_ns=BASE + 1, fill_price=10, stop_price=9, trades=rows, bars=[])

    def test_new_source_segment_can_restart_source_ordinal(self):
        rows = envelopes([trade(2, 12), trade(3, 10)])
        rows[1].update(source_artifact_id=456, source_request_id="tail", source_record_ordinal=0)
        out = m.project_external_fill_proxy(window=window(), fill_time_ns=BASE + 1, fill_price=10, stop_price=9, trades=rows, bars=[])
        self.assertEqual([leg["trade_evidence"]["source_artifact_id"] for leg in out["legs"]], [123, 456])

    def test_full_input_is_validated_even_after_terminal_proxy(self):
        with self.assertRaises(ValueError):
            project([trade(2, 8), trade(3, float("nan"))])

    def test_randomized_synthetic_leg_parity_with_frozen_external_fill_engine(self):
        rng = random.Random(74019)
        for case in range(120):
            fill_ns = BASE + rng.randrange(0, 5 * m.MINUTE_NS)
            fill = rng.choice([4.13, 10.0, 16.725])
            stop = fill - rng.choice([0.13, 0.5, 1.0])
            trades = [trade(offset, fill + rng.uniform(-2, 3), rng.choice([["@"], ["I"], ["UNKNOWN"], ["I", "Z"]]))
                for offset in sorted(rng.randrange(0, m.SIGNAL_NS + m.TAIL_NS) for _ in range(70))]
            bars = [bar(i, 10, rng.choice([9.9, 10, 10.1])) for i in range(16)]
            actual = project(trades, bars, fill_time_ns=fill_ns, fill_price=fill, stop_price=stop)
            trade_frame = pd.DataFrame({"price": [r["p"] for r in trades], "conditions": [r["c"] for r in trades],
                "tape": [r["z"] for r in trades]}, index=pd.DatetimeIndex([pd.Timestamp(r["t"]) for r in trades]))
            usable = [b for b in bars if int(pd.Timestamp(b["t"]).value) + m.MINUTE_NS <= window()["signal_end_ns"]]
            bar_frame = pd.DataFrame({"open": [b["o"] for b in usable], "close": [b["c"] for b in usable]},
                index=pd.DatetimeIndex([pd.Timestamp(b["t"]) for b in usable]))
            expected = legacy.simulate_external_fill_management(symbol="SYNTHETIC", fill_time=pd.Timestamp(fill_ns, unit="ns", tz="UTC"),
                fill_price=fill, stop_price=stop, bars=bar_frame, trades=trade_frame)
            self.assertEqual([(l["reason"], l["exit_time_ns"], l["proxy_price"], l["quantity_fraction"], l["execution_via_odd_lot"]) for l in actual["legs"]],
                [(l.reason.value, int(l.exit_time.value), l.exit_price, l.quantity_fraction, l.execution_via_odd_lot) for l in expected.legs], case)
            for key in ("remaining_fraction", "active_stop_price", "first_target_price", "target_touched", "stop_moved_to_breakeven"):
                self.assertEqual(actual[key], getattr(expected, key), (case, key))

    def test_exit_envelope_exact_nanoseconds_and_midnight(self):
        decision = BASE + 123456789
        out = m.conditional_exit_envelope(window(), decision)
        self.assertEqual(out["quote_start_ns"], decision - 100_000_000)
        self.assertEqual(out["end_ns"], decision + 550_000_001)
        self.assertEqual(out["status_start_ns"], int(pd.Timestamp("2025-05-30T00:00:00Z").value))
        self.assertTrue(out["fits_frozen_envelope"])
        self.assertFalse(out["request_authorized"])
        self.assertFalse(out["order_authorized"])

    def test_exit_tail_edge_censored_without_window_extension(self):
        w = window()
        last = w["end_ns"] - m.POST_QUOTE_NS - 1
        self.assertTrue(m.conditional_exit_envelope(w, last)["fits_frozen_envelope"])
        out = m.conditional_exit_envelope(w, last + 1)
        self.assertFalse(out["fits_frozen_envelope"])
        self.assertEqual(out["status"], "unavailable_required_exit_tail_outside_frozen_envelope")
        self.assertEqual(out["original_opportunity_end_ns"], w["end_ns"])

    def test_scenario_requirements_equal_frozen_execution_policies(self):
        requirements = m.exit_requirements()
        for row, policy, offset in zip(requirements["scenarios"],
                (execution.BASELINE_CONSERVATIVE_POLICY, execution.STRESS_POLICY), (5, 2), strict=True):
            self.assertEqual(row["scenario_id"], policy.policy_id)
            self.assertEqual(row["arrival_latency_ns"], policy.decision_to_arrival_ms * 1_000_000)
            self.assertEqual(row["max_quote_age_ns"], policy.max_quote_age_ms * 1_000_000)
            self.assertEqual(row["cancel_after_arrival_ns"], policy.cancel_after_arrival_ms * 1_000_000)
            self.assertEqual(row["cancel_ack_latency_ns"], policy.cancel_ack_ms * 1_000_000)
            self.assertEqual(row["displayed_size_haircut"], str(policy.displayed_size_participation))
            self.assertEqual(row["limit_offset_ticks"], offset)
        self.assertEqual(requirements["actual_request_count"], 0)
        self.assertFalse(requirements["exit_execution_implementation_registered"])
        self.assertFalse(requirements["descriptive_target_touch_is_confirmed_fill"])
        self.assertGreaterEqual(len(requirements["unresolved_required_bindings"]), 9)

    def test_metadata_preserves_full_population_without_running_primitive(self):
        with patch.object(m, "project_external_fill_proxy", side_effect=AssertionError("historical projection forbidden")), \
             patch.object(m.inputs, "ManagementInputBundle", side_effect=AssertionError("source tapes remain unopened")):
            bundle = m.build_bundle(ROOT)
        index = json.loads(bundle["projection-input-requirements.json"])
        original = m.frozen(ROOT / m.inputs.SNAPSHOT_PATH / "opportunity-input-index.json")
        self.assertEqual(index["opportunity_windows"], original["opportunity_windows"])
        self.assertEqual(index["dates"], original["dates"])
        self.assertEqual(index["counts"], {"opportunities": 109, "available_entry_inputs": 86, "unavailable_entry_inputs": 23,
            "dates": 30, "no_decision_dates": 5, "account_paths": 12, "session_slots": 360, "profile_scenario_opportunity_references": 744})
        for raw in bundle.values():
            payload = json.loads(raw)
            for key, value in m.BOUNDARY.items():
                self.assertEqual(payload[key], value)

    def test_bundle_is_deterministic_write_once_and_tamper_evident(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "bundle"
            self.assertTrue(m.write_bundle(ROOT, output)["verification_passed"])
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            self.assertEqual(before, m.build_bundle(ROOT))
            with self.assertRaises(FileExistsError):
                m.write_bundle(ROOT, output)
            (output / "readiness-report.json").write_bytes(b"{}\n")
            with self.assertRaisesRegex(ValueError, "reconstruction differs"):
                m.verify_bundle(ROOT, output)

    def test_wrong_repository_output_and_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, "cannot overwrite"):
            m.write_bundle(ROOT, ROOT / "research/runtime/other")
        with tempfile.TemporaryDirectory() as temp:
            link = Path(temp) / "link"
            link.symlink_to(ROOT / m.inputs.SNAPSHOT_PATH, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                m.verify_bundle(ROOT, link)

    def test_cli_is_offline_metadata_only_and_has_no_historical_run_mode(self):
        result = subprocess.run([sys.executable, str(ROOT / m.SCRIPT_PATH), "--validate-registration"],
            cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(result.stdout)["verification_passed"])
        rejected = subprocess.run([sys.executable, str(ROOT / m.SCRIPT_PATH), "--run"], cwd=ROOT, capture_output=True)
        self.assertNotEqual(rejected.returncode, 0)
        text = (ROOT / m.SCRIPT_PATH).read_text()
        self.assertLess(text.index("sys.addaudithook(deny_external_io)"), text.index("from momentumbot.research import"))

    def test_workflow_is_read_only_offline_and_hash_locked(self):
        text = (ROOT / m.WORKFLOW_PATH).read_text()
        workflow = yaml.safe_load(text)
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertIn("--require-hashes --only-binary=:all: --no-deps", text)
        self.assertIn("python -O -m unittest", text)
        self.assertNotIn("secrets.", text)
        self.assertNotIn("workflow_dispatch:", text)
        self.assertNotIn("download-artifact", text)


if __name__ == "__main__":
    unittest.main()
