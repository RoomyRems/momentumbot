from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import gzip
from pathlib import Path
import tempfile
import unittest
import zipfile

import pandas as pd
from pandas.testing import assert_frame_equal

from momentumbot.research import sealed_historical_setup_stop_audit_v01 as a

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    index = pd.date_range("2025-06-02T11:00:00Z", periods=6, freq="10s")
    bars = pd.DataFrame([(4, 4.1, 3.98, 4.08, 100), (4.08, 4.3, 4.05, 4.28, 200),
        (4.28, 4.55, 4.25, 4.52, 300), (4.52, 4.8, 4.5, 4.75, 400),
        (4.75, 4.76, 4.62, 4.65, 100), (4.65, 4.7, 4.6, 4.68, 80)],
        columns=["open", "high", "low", "close", "volume"], index=index)
    support = pd.DataFrame({"vwap": [4.4], "ema": [4.5]}, index=index[4:5])
    times = pd.to_datetime(["2025-06-02T11:01:01Z", "2025-06-02T11:01:02Z"])
    trades = pd.DataFrame({"price": [4.71, 4.72], "size": [100, 200], "conditions": [["@"], ["@"]], "tape": ["C", "C"]}, index=times)
    activation = a.daily.ProfileActivation("activation-synthetic", "TEST", index[0].isoformat(), "c" * 64, ("synthetic",))
    decisions = a.daily.build_micro_trigger_decisions(activation, bars=bars, trades=trades,
        support=support, replay_end=pd.Timestamp("2025-06-02T14:00:00Z"))
    assert len(decisions) == 1
    source = {"opportunity_id": "op-synthetic", "source_decision": a.daily._json_value(asdict(decisions[0])),
        "window": {"opportunity": {"trading_date": "2025-06-02"}}, "entry": {"input_status": "available", "reason": "available"}}
    macd = pd.DataFrame({"macd": [0.1], "signal": [0.11], "histogram": [-0.01]}, index=index[3:4])
    return source, bars, a.chart_source(trades), support, macd


class SourceMechanicsTests(unittest.TestCase):
    def test_aggregation_preserves_conditions_float_arithmetic_and_ties(self):
        offsets = [0, 0, 3, 4, 5, 8, 9, 10, 11, 20, 21, 30, 31]
        trades = pd.DataFrame({"price": [1.1, 1.13, 90, 1.14, 90, 1.12, 90, 70, 80, 1.11, 1.15, 8, 9],
            "size": [101, 201, 1, 7, 5, 55, 99, 1, 1, 11, 13, 1, 1],
            "conditions": [["@"], [], ["I"], ["B"], ["B"], ["@", "T"], ["unknown"], ["I"], ["Q"], ["@"], ["@"], ["M"], ["unknown"]],
            "tape": ["C", "C", "C", "C", "A", "C", "C", "C", "C", "C", "C", "C", "C"]},
            index=pd.Timestamp("2025-06-02T11:00:00Z") + pd.to_timedelta(offsets, unit="s"))
        for unit in ("ns", "us", "ms", "s"):
            resolved = trades.copy()
            resolved.index = resolved.index.as_unit(unit)
            for frame in (resolved, resolved.iloc[::-1], resolved.iloc[:0]):
                with self.subTest(unit=unit, length=len(frame), reversed=not frame.index.is_monotonic_increasing):
                    assert_frame_equal(a.aggregate_source(frame), a.micro_bars.aggregate_trade_bars(frame), check_exact=True)
                    assert_frame_equal(a.chart_source(frame), a.micro_execution.price_eligible_trades(frame), check_exact=True)

    def test_serialization_matches_original_including_numeric_coercion(self):
        _, bars, chart, support, _ = fixture()
        for frame in (bars, chart, support, bars.iloc[:0], chart.iloc[:0]):
            self.assertEqual(a.frame_payload(frame, pd.Timestamp("2025-06-02T11:01:01Z")),
                a.daily._frame_prefix(frame, through=pd.Timestamp("2025-06-02T11:01:01Z")))

    def test_witness_preserves_unknown_indicator_values(self):
        frame = pd.DataFrame({"macd": [float("nan"), 0.2]}, index=pd.date_range("2025-06-02T11:00Z", periods=2, freq="min"))
        packed = a.pack_frame(frame, frame.index[-1])
        self.assertIsNone(packed["rows"][0][1])
        assert_frame_equal(a.unpack_frame(packed), frame, check_freq=False)

    def test_witness_rejects_repeated_clocks(self):
        _, bars, _, _, _ = fixture()
        packed = a.pack_frame(bars, bars.index[-1])
        packed["rows"].append(packed["rows"][-1])
        with self.assertRaisesRegex(ValueError, "repeat or reverse"):
            a.unpack_frame(packed)

    def test_original_archive_identity_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.zip"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("retained.json", "{}")
            spec = {"bytes": path.stat().st_size, "sha256": a.sha(path.read_bytes()), "members": 1}
            archive = a.SourceArchive(path, spec)
            self.assertEqual(archive.read("retained.json"), b"{}")
            archive.close()
            with self.assertRaisesRegex(ValueError, "bytes differ"):
                a.SourceArchive(path, {**spec, "sha256": "0" * 64})

    def test_archive_path_traversal_is_rejected_even_with_matching_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.zip"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("../retained.json", "{}")
            with self.assertRaisesRegex(ValueError, "unsafe"):
                a.SourceArchive(path, {"bytes": path.stat().st_size, "sha256": a.sha(path.read_bytes())})


class CausalityTests(unittest.TestCase):
    def test_independent_original_builder_prefix_and_stop_reproduce(self):
        inputs = fixture()
        result = a.reconstruct_decision(*inputs)
        self.assertTrue(result["original_prefix_matches"])
        self.assertEqual(result["features"]["pullback_number"], 1)
        self.assertEqual(result["planned_risk_per_share_usd"], "0.11")
        self.assertEqual(result["room_to_original_peak_r"], "0.818182")
        self.assertTrue(result["room_below_2r"])

    def test_changed_original_stop_or_ordinal_is_rejected(self):
        for key, value in (("stop_price", 4.61), ("pullback_number", 2)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "geometry, ordinal or stop"):
                args = fixture()
                args[0]["source_decision"]["plan"][key] = value
                a.reconstruct_decision(*args)

    def test_future_prices_and_indicators_do_not_change_result(self):
        source, bars, chart, support, macd = fixture()
        expected = a.reconstruct_decision(source, bars, chart, support, macd)
        bars.loc[bars.index[-1] + pd.Timedelta(seconds=10)] = [100, 200, 1, 50, 1000000]
        chart.loc[chart.index[-1], "price"] = 1000
        support.loc[support.index[-1] + pd.Timedelta(minutes=1)] = [1000, 1000]
        macd.loc[macd.index[-1] + pd.Timedelta(minutes=1)] = [-1000, -1000, -1000]
        self.assertEqual(a.reconstruct_decision(source, bars, chart, support, macd), expected)

    def test_support_later_than_trough_cannot_make_plan(self):
        args = list(fixture())
        args[3].index = args[3].index + pd.Timedelta(minutes=1)
        with self.assertRaisesRegex(ValueError, "geometry, ordinal or stop"):
            a.reconstruct_decision(*args)

    def test_equal_timestamp_source_rows_still_bind_prefix(self):
        args = list(fixture())
        chart = args[2]
        chart = pd.concat([chart.iloc[:1], chart.iloc[:1], chart.iloc[1:]])
        args[2] = chart
        with self.assertRaisesRegex(ValueError, "causal prefix hash"):
            a.reconstruct_decision(*args)

    def test_later_crossing_cannot_replace_first_crossing(self):
        args = list(fixture())
        args[2] = args[2].iloc[1:]
        with self.assertRaisesRegex(ValueError, "first causal chart crossing"):
            a.reconstruct_decision(*args)

    def test_room_is_signed_and_nonpositive_denominators_stay_unknown(self):
        self.assertEqual(a.signed_ratio(Decimal("-.1"), Decimal(".2")), "-0.500000")
        self.assertIsNone(a.signed_ratio(Decimal(".1"), Decimal(0)))

    def test_macd_unknown_and_zero_remain_distinct(self):
        args = list(fixture())
        args[4].loc[:, "macd"] = float("nan")
        self.assertIsNone(a.reconstruct_decision(*args)["macd_line_nonpositive"])
        args[4].loc[:, "macd"] = 0
        self.assertTrue(a.reconstruct_decision(*args)["macd_line_nonpositive"])

    def test_quote_lookback_is_inclusive_and_separate_from_sip_clock(self):
        row = a.reconstruct_decision(*fixture())
        at = a.loss.baseline.timestamp_ns(row["source_decision"]["decision_at"])
        for age in (0, 100_000_000):
            ref = {"ask_price": "4.72", "bid_price": "4.71", "ts_recv_ns": at - age}
            alignment = a.alignment(row, ref)
            self.assertEqual(alignment["quote_age_ns"], age)
            self.assertEqual(alignment["ask_minus_sip_trigger_usd"], "0.01")
        for age in (-1, 100_000_001):
            with self.assertRaisesRegex(ValueError, "clock/spread"):
                a.alignment(row, {"ask_price": "4.72", "bid_price": "4.71", "ts_recv_ns": at - age})

    def test_unavailable_quote_cannot_be_invented_or_available_quote_dropped(self):
        row = a.reconstruct_decision(*fixture())
        with self.assertRaisesRegex(ValueError, "lost its reference"):
            a.alignment(row, None)
        row["original_input_status"] = "unavailable"
        self.assertIsNone(a.alignment(row, None))
        with self.assertRaisesRegex(ValueError, "gained a reference"):
            a.alignment(row, {})


class FrozenEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = a.accepted.read_json((ROOT / f"research/strategy/{a.ID}.json").read_bytes())
        cls.expected = cls.contract["content_sha256"]
        cls.report = a.accepted.read_json((ROOT / a.BASE / "report.json").read_bytes())
        cls.witness = a.accepted.read_json(gzip.decompress((ROOT / a.BASE / "geometry-witnesses.json.gz").read_bytes()))
        cls.previous, cls.binding, cls.refs = a.original_evidence(ROOT)

    def test_frozen_registration_and_saved_geometry_reproduce(self):
        self.assertEqual(a.check_registration(ROOT, self.expected), self.contract)
        a.verify_result(self.report, self.witness, self.expected, self.previous, self.binding, self.refs)
        self.assertEqual((ROOT / a.BASE / "report.md").read_text(), a.render_markdown(self.report))

    def test_every_alternative_and_unavailable_reference_is_retained(self):
        self.assertEqual(len(self.report["selected_dates"]), 30)
        self.assertEqual(self.report["population"]["sessions"], 360)
        self.assertEqual(self.report["population"]["unavailable_references"], 162)
        for actual, original in zip(self.report["paths"], self.previous["paths"]):
            self.assertEqual(actual["original_totals"], original["totals"])
            self.assertEqual(actual["original_decisions"], original["decisions"])

    def test_changed_descriptive_field_cannot_be_resigned_into_evidence(self):
        for key, value in (("planned_risk_per_share_usd", "999"), ("room_to_original_peak_r", "999"),
                ("completed_minute_macd", None), ("support_available_at", "2000-01-01T00:00:00Z")):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "descriptive geometry or MACD"):
                report = deepcopy(self.report)
                report["opportunities"][0][key] = value
                a.verify_result(a.seal(report), self.witness, self.expected, self.previous, self.binding, self.refs)

    def test_changed_summary_or_authority_cannot_be_resigned(self):
        for key, value in (("selected_dates", []), ("all_300_original_stops_match", False),
                ("account_replay_executed", True), ("opportunities_with_room_below_2r", 999)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "totals, cohorts or authority"):
                a.verify_result(a.seal({**self.report, key: value}), self.witness, self.expected, self.previous, self.binding, self.refs)

    def test_mutated_geometry_witness_cannot_pass_original_plan(self):
        witness = deepcopy(self.witness)
        row = self.report["opportunities"][0]
        group = witness["groups"][row["witness_key"]]["micro"]
        for bar in group["rows"]:
            if bar[0] == row["source_decision"]["plan"]["source_bar_start"]:
                bar[1 + group["columns"].index("low")] = 0.01
        witness = a.seal(witness)
        report = a.seal({**self.report, "witness_content_sha256": witness["content_sha256"]})
        with self.assertRaisesRegex(ValueError, "geometry, ordinal or stop"):
            a.verify_result(report, witness, self.expected, self.previous, self.binding, self.refs)

    def test_wrong_external_commitment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "external setup audit commitment"):
            a.check_registration(ROOT, "0" * 64)

    def test_publication_repair_preserves_every_original_observation(self):
        original = a.repair_parent_report(ROOT)
        a.unchanged_observations(self.report, original)
        changed = deepcopy(self.report)
        changed["opportunities"][0]["trigger"]["price"] = "999"
        with self.assertRaisesRegex(ValueError, "changed original audit observations"):
            a.unchanged_observations(changed, original)


if __name__ == "__main__":
    unittest.main()
