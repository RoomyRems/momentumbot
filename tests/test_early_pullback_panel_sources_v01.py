from copy import deepcopy
import io
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile

import pandas as pd

from momentumbot.research import early_pullback_panel_sources_v01 as a
from tests.test_early_pullback_paired_adapter_v01 import causal_source, pack

ROOT = Path(__file__).resolve().parents[1]


def calendar():
    return {"scope": a.SCOPE, "sessions": a.calendar_rows()}


def catalogue():
    value = calendar()
    return a.build_catalogue(value, expected_calendar_sha256=a.fingerprint(value))


def day_source(day=a.DATES[0], *, ordinal=1, empty=False):
    symbol = "SYNTHETICA"
    decision = {"symbol": symbol, "activation_id": "synthetic-source-template",
        "decision_at": a._local(day, 8, 1).isoformat(),
        "eligible_strategy_profile_ids": [a.parent.daily.GENERAL_PROFILE_ID, a.parent.daily.SMALL_PROFILE_ID]}
    source = causal_source(decision, ordinal=ordinal)
    minutes = a.parent._frame(source["session_minutes"], a.OHLCV)
    minutes["volume"] = 10000
    raw = minutes[["close", "volume"]].copy()
    split = raw[["close"]] / 2
    q = source["activation"]["candidate_qualified_at"]
    scanner = {"candidate_rows": [] if empty else [{"symbol": symbol, "previous_close": 2.0,
        "first_market_qualified_bar_started_at": (pd.Timestamp(q) - pd.Timedelta(minutes=1)).isoformat(),
        "first_market_qualified_at": q}],
        "float_records": [] if empty else [{"symbol": symbol, "float_classification": "pass", "float_pillar_pass": True,
            "estimated_float_shares": 5000000, "float_asof": (a._local(day) - pd.Timedelta(days=1)).isoformat(),
            "method": "synthetic-causal-float", "sec_status": "success"}],
        "news_events": [], "news_statuses": [] if empty else [{"symbol": symbol, "provider_status": "success"}],
        "membership_symbols": [symbol], "previous_close_by_symbol": {symbol: 2.0},
        "rank_split_minute_bars_by_symbol": {symbol: pack(split)},
        "candidate_raw_minute_bars_by_symbol": {} if empty else {symbol: pack(raw)},
        "candidate_exact_rvol_by_symbol": {} if empty else {symbol: pack(pd.DataFrame({"relative_volume": 10.0}, index=raw.index))}}
    warmup = a.parent._frame(source["ema_warmup"], a.OHLCV)
    for key in ("open", "high", "low", "close"):
        warmup[key] /= 2
    warmup["vwap"] = warmup["close"]
    return {"scope": a.SCOPE, "trading_date": day, "scanner": scanner,
        "micro_by_symbol": {} if empty else {symbol: {"trades": source["trades"],
            "session_minutes_raw": pack(minutes), "ema_warmup_split": pack(warmup)}}}


def bind(value):
    return a.bind_day(value, expected_source_sha256=a.fingerprint(value), expected_day=value["trading_date"])


def archive_fixture(path, *, changes=None, extra=None, unsafe=False, duplicate=False):
    values = {"calendar.json": calendar()}
    values.update({f"dates/{d}.json": day_source(d, empty=True) for d in a.DATES})
    values[f"dates/{a.DATES[0]}.json"] = day_source()
    values.update(changes or {})
    files = {name: a.parent.selection.encoded(value) for name, value in values.items() if value is not None}
    files.update(extra or {})
    manifest = {"contract_id": a.ID, "scope": a.SCOPE, "selected_dates": list(a.DATES),
        "files": {name: {"bytes": len(raw), "sha256": a.sha(raw)} for name, raw in files.items()}}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", a.parent.selection.encoded(manifest))
            for name, raw in files.items():
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                if unsafe and name == "calendar.json":
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, raw)
            if duplicate:
                archive.writestr("calendar.json", files["calendar.json"])
    raw = path.read_bytes()
    return {"expected_archive": {"bytes": len(raw), "sha256": a.sha(raw)},
            "expected_manifest_sha256": a.fingerprint(manifest)}


class CatalogueTests(unittest.TestCase):
    def test_exact_24_paths_720_new_date_slots_and_once_only_seeds(self):
        value = catalogue()
        self.assertEqual(len(value["paths"]), 24)
        self.assertEqual(len({p["path_id"] for p in value["paths"]}), 24)
        self.assertEqual(sum(len(p["sessions"]) for p in value["paths"]), 720)
        for path in value["paths"]:
            self.assertEqual(sum(s["seed_applied"] for s in path["sessions"]), 1)
            self.assertEqual([s["trading_date"] for s in path["sessions"]], list(a.DATES))
            self.assertEqual(path["seed"]["equity_usd"], a.parent.accounts.ACCOUNT_SEEDS[path["account_key"]])
            for i, slot in enumerate(path["sessions"]):
                self.assertEqual(slot["previous_session_id"], None if i == 0 else path["sessions"][i - 1]["session_id"])
                self.assertIsNone(slot["source_date_has_no_micro_decisions"])

    def test_dst_conversion_preserves_full_new_york_session(self):
        rows = calendar()["sessions"]
        self.assertEqual(pd.Timestamp(rows[0]["open"]).tz_convert("UTC").hour, 14)
        self.assertEqual(pd.Timestamp(rows[3]["open"]).tz_convert("UTC").hour, 13)
        value = calendar()
        for row in value["sessions"]:
            row.update(open=pd.Timestamp(row["open"]).tz_convert("UTC").isoformat(),
                       close=pd.Timestamp(row["close"]).tz_convert("UTC").isoformat())
        self.assertEqual(len(a.build_catalogue(value, expected_calendar_sha256=a.fingerprint(value))["paths"]), 24)

    def test_missing_replaced_reordered_half_day_or_naive_calendar_rejected(self):
        for kind in ("missing", "replaced", "reordered", "early_close", "naive"):
            value = calendar()
            if kind == "missing": value["sessions"].pop()
            elif kind == "replaced": value["sessions"][0]["date"] = "2026-03-11"
            elif kind == "reordered": value["sessions"].reverse()
            elif kind == "early_close": value["sessions"][0]["close"] = a._local(a.DATES[0], 13).isoformat()
            else: value["sessions"][0]["open"] = "2026-03-04T09:30:00"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                a.build_catalogue(value, expected_calendar_sha256=a.fingerprint(value))

    def test_external_pin_and_catalogue_tamper_rejected(self):
        with self.assertRaises(ValueError):
            a.build_catalogue(calendar(), expected_calendar_sha256="0" * 64)
        value = catalogue()
        self.assertEqual(a.validate_catalogue(value, expected_catalogue_sha256=a.fingerprint(value)), value)
        value["paths"][0]["sessions"][1]["seed_applied"] = True
        with self.assertRaises(ValueError):
            a.validate_catalogue(value, expected_catalogue_sha256=a.fingerprint(value))

    def test_original_date_guard_unchanged_and_rejects_new_slots(self):
        old = tuple(a.parent.accounts.DATES)
        with self.assertRaises((ValueError, KeyError)):
            a.parent.accounts._validate_slot(catalogue()["paths"][0]["sessions"][0])
        self.assertEqual(tuple(a.parent.accounts.DATES), old)
        self.assertFalse(set(old).intersection(a.DATES))


class DaySourceTests(unittest.TestCase):
    def test_scanner_normalization_original_micro_and_first_two_reproduce(self):
        for ordinal in (1, 2, 3):
            with self.subTest(ordinal=ordinal):
                result = bind(day_source(ordinal=ordinal))
                self.assertTrue(result["activations"])
                self.assertTrue(result["decisions"])
                self.assertEqual(result["normalization_evidence"]["SYNTHETICA"]["raw_to_split_factor"], 2.0)
                last = result["sources"][result["decisions"][-1]["plan_id"]]
                self.assertEqual(last["binding"]["selection"]["pullback_number"], ordinal)
                self.assertEqual(last["binding"]["selection"]["selected"], ordinal <= 2)
                self.assertFalse(result["archive_bytes_verified"])

    def test_parent_profile_grouping_agrees_except_child_identity(self):
        value = day_source()
        inputs = a.scanner_inputs(value["scanner"], value["trading_date"])
        rows = a.scanner.build_scanner_snapshot_rows(trading_date=a.date.fromisoformat(value["trading_date"]),
            profile=a.historical_profile_union_v0_1(), **inputs)
        original, _ = a.parent.daily.build_profile_activations(scanner_runtime_content_sha256=a.fingerprint(rows), scanner_rows=rows)
        actual = a.activation_rows(rows, value["trading_date"])
        self.assertEqual([{k: v for k, v in a.parent.json_safe(a.asdict(row)).items() if k != "activation_id"} for row in original],
                         [{k: v for k, v in row.items() if k != "activation_id"} for row in actual])

    def test_missing_micro_cannot_be_no_trigger_or_filter_opportunity(self):
        value = day_source()
        value["micro_by_symbol"] = {}
        with self.assertRaisesRegex(ValueError, "exact activated-symbol"):
            bind(value)

    def test_verified_no_candidate_and_verified_empty_trade_tape_are_distinct(self):
        empty = bind(day_source(empty=True))
        self.assertTrue(empty["no_micro_decisions"])
        self.assertEqual(empty["activations"], [])
        value = day_source()
        tape = value["micro_by_symbol"]["SYNTHETICA"]["trades"]
        tape["index"], tape["data"] = [], []
        result = bind(value)
        self.assertTrue(result["no_micro_decisions"])
        self.assertTrue(result["activations"])

    def test_dropped_census_rank_or_candidate_source_rejected(self):
        for key in ("rank_split_minute_bars_by_symbol", "previous_close_by_symbol", "candidate_exact_rvol_by_symbol"):
            value = day_source()
            value["scanner"][key] = {}
            with self.subTest(key=key), self.assertRaises(ValueError):
                bind(value)

    def test_factor_tamper_inconsistent_basis_and_raw_bridge_rejected(self):
        for kind in ("unstable", "raw_bridge", "missing_pair"):
            value = day_source()
            scanner = value["scanner"]
            if kind == "unstable": scanner["rank_split_minute_bars_by_symbol"]["SYNTHETICA"]["data"][0][0] *= 2
            elif kind == "raw_bridge":
                frame = value["micro_by_symbol"]["SYNTHETICA"]["session_minutes_raw"]
                frame["data"][0][frame["columns"].index("close")] += .01
            else:
                frame = scanner["rank_split_minute_bars_by_symbol"]["SYNTHETICA"]
                frame["index"].pop(); frame["data"].pop()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                bind(value)

    def test_future_news_does_not_change_earlier_activation_or_prefix(self):
        value = day_source()
        before = bind(value)
        value["scanner"]["news_events"].append({"symbol": "SYNTHETICA", "headline_id": "future-test",
            "published_at": a._local(a.DATES[0], 9).isoformat()})
        after = bind(value)
        self.assertEqual(before["activations"], after["activations"])
        self.assertEqual(before["decisions"], after["decisions"])

    def test_later_trade_never_enters_earlier_source_prefix(self):
        value = day_source()
        before = bind(value)
        trades = value["micro_by_symbol"]["SYNTHETICA"]["trades"]
        trades["index"].append(a._local(a.DATES[0], 8, 2).isoformat())
        trades["data"].append([50.0, 100, ["@"], "C"])
        after = bind(value)
        for plan, source in before["sources"].items():
            self.assertEqual(source, after["sources"][plan])

    def test_warmup_session_clock_and_noncausal_support_rejected(self):
        for field in ("ema_warmup_split", "session_minutes_raw", "trades"):
            value = day_source()
            frame = value["micro_by_symbol"]["SYNTHETICA"][field]
            frame["index"][-1] = a._local(a.DATES[0], 10).isoformat()
            with self.subTest(field=field), self.assertRaises(ValueError):
                bind(value)

    def test_labels_extra_market_columns_and_real_symbol_rejected(self):
        for kind in ("label", "nested", "column", "real"):
            value = day_source()
            if kind == "label": value["ross_action"] = "buy"
            elif kind == "nested": value["scanner"]["candidate_rows"][0]["future_return"] = 100
            elif kind == "column":
                frame = value["micro_by_symbol"]["SYNTHETICA"]["trades"]
                frame["columns"].append("pnl")
                for row in frame["data"]: row.append(100)
            else: value["scanner"]["membership_symbols"] = ["AAPL"]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                bind(value)

    def test_new_dates_and_synthetic_scope_are_not_caller_selectable(self):
        value = day_source()
        value["scope"] = "historical"
        with self.assertRaises(ValueError): bind(value)
        value = day_source()
        with self.assertRaises(ValueError):
            a.bind_day(value, expected_source_sha256=a.fingerprint(value), expected_day="2026-03-11")

    def test_input_immutability_and_unverified_provenance_not_overclaimed(self):
        value = day_source()
        saved = deepcopy(value)
        result = bind(value)
        self.assertEqual(value, saved)
        for key in ("provider_origin_authenticated", "point_in_time_universe_provenance_authenticated",
                    "market_candidate_discovery_recomputed", "provider_request_exhaustion_verified",
                    "historical_zero_opportunity_claim", "historical_account_context_adapter_integrated"):
            self.assertFalse(result[key])

    def test_tied_receive_order_and_source_pin_preserved(self):
        value = day_source()
        before = bind(value)
        tape = value["micro_by_symbol"]["SYNTHETICA"]["trades"]
        tape["index"].append(tape["index"][-1])
        tape["data"].append([10.0, 101, ["@"], "C"])
        after = bind(value)
        old = before["decisions"][-1]
        new = after["decisions"][-1]
        self.assertEqual(old["plan_id"], new["plan_id"])
        self.assertNotEqual(old["micro_runtime_content_sha256"], new["micro_runtime_content_sha256"])
        with self.assertRaises(ValueError):
            a.bind_day(value, expected_source_sha256=a.fingerprint(day_source()), expected_day=a.DATES[0])

    def test_active_source_reconstruction_crosses_dst_and_last_panel_date(self):
        results = [bind(day_source(day)) for day in (a.DATES[0], a.DATES[3], a.DATES[-1])]
        self.assertEqual(len({r["activations"][0]["activation_id"] for r in results}), 3)
        for day, result in zip((a.DATES[0], a.DATES[3], a.DATES[-1]), results):
            self.assertTrue(result["decisions"])
            for decision in result["decisions"]:
                self.assertEqual(pd.Timestamp(decision["decision_at"]).tz_convert("America/New_York").date().isoformat(), day)
                self.assertEqual(result["sources"][decision["plan_id"]]["binding"]["original_decision_sha256"], a.fingerprint(decision))


class ArchiveTests(unittest.TestCase):
    def test_byte_verified_full_panel_retains_all_dates_and_same_arm_source_union(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.zip"
            pins = archive_fixture(path)
            with a.SourceArchive(path, **pins) as archive:
                result = a.bind_panel(archive)
        self.assertEqual(list(result["days"]), list(a.DATES))
        self.assertEqual(len(result["paths"]), 24)
        self.assertEqual(sum(len(p["sessions"]) for p in result["paths"]), 720)
        self.assertTrue(all(d["archive_bytes_verified"] for d in result["days"].values()))
        control, child = result["paths"][:12], result["paths"][12:]
        for one, two in zip(control, child):
            self.assertEqual([s["opportunity_ids"] for s in one["sessions"]], [s["opportunity_ids"] for s in two["sessions"]])
            self.assertTrue(all(s["execution_input_status"] == "not_acquired" and not s["account_runtime_executed"] for s in one["sessions"]))

    def test_archive_and_manifest_external_pins_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.zip"
            pins = archive_fixture(path)
            for key in ("archive", "manifest"):
                bad = deepcopy(pins)
                if key == "archive": bad["expected_archive"]["sha256"] = "0" * 64
                else: bad["expected_manifest_sha256"] = "0" * 64
                with self.subTest(key=key), self.assertRaises(ValueError):
                    a.SourceArchive(path, **bad)

    def test_missing_date_extra_file_duplicate_and_symlink_rejected(self):
        for kind in ("missing", "extra", "duplicate", "symlink", "traversal"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "capture.zip"
                kwargs = {"changes": {f"dates/{a.DATES[-1]}.json": None}} if kind == "missing" else {}
                if kind == "extra": kwargs["extra"] = {"outcomes.json": b"{}"}
                if kind == "traversal": kwargs["extra"] = {"../outside.json": b"{}"}
                pins = archive_fixture(path, duplicate=kind == "duplicate", unsafe=kind == "symlink", **kwargs)
                with self.assertRaises(ValueError): a.SourceArchive(path, **pins)

    def test_duplicate_json_key_and_mutated_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.zip"
            pins = archive_fixture(path, extra={"calendar.json": b'{"scope":"x","scope":"y"}'})
            with self.assertRaisesRegex(ValueError, "duplicate"):
                a.SourceArchive(path, **pins)
            pins = archive_fixture(path)
            with a.SourceArchive(path, **pins) as archive:
                archive.manifest["files"]["calendar.json"]["sha256"] = "0" * 64
                with self.assertRaises(ValueError): archive.read("calendar.json")

    def test_member_tamper_rejected_even_with_new_outer_archive_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.zip"
            pins = archive_fixture(path)
            with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as old:
                files = {name: old.read(name) for name in old.namelist()}
            name = f"dates/{a.DATES[0]}.json"
            files[name] = files[name].replace(b'"SYNTHETICA"', b'"SYNTHETICB"')
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as changed:
                for name, raw in files.items(): changed.writestr(name, raw)
            pins["expected_archive"] = {"bytes": path.stat().st_size, "sha256": a.sha(path.read_bytes())}
            with self.assertRaisesRegex(ValueError, "member bytes"):
                a.SourceArchive(path, **pins)

    def test_wrong_day_content_and_altered_catalogue_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.zip"
            pins = archive_fixture(path, changes={f"dates/{a.DATES[0]}.json": day_source(a.DATES[1])})
            with a.SourceArchive(path, **pins) as archive:
                with self.assertRaises(ValueError): archive.bind_day(a.DATES[0])
            pins = archive_fixture(path)
            with a.SourceArchive(path, **pins) as archive:
                archive.catalogue["paths"][0]["seed"]["equity_usd"] = "40000.00"
                with self.assertRaisesRegex(ValueError, "verified calendar"):
                    a.bind_panel(archive)


class RegistrationTests(unittest.TestCase):
    def test_registration_binds_unchanged_parent_and_closed_authority(self):
        value = a.validate_registration(ROOT)
        self.assertEqual(value["parent_commit"], a.PARENT)
        self.assertEqual(value["selected_dates"], list(a.DATES))
        self.assertEqual(a.parent.validate_registration(ROOT)["content_sha256"], a.PARENT_SHA)
        for key, value in a.BOUNDARY.items():
            self.assertEqual(value, key == "synthetic_only")


if __name__ == "__main__":
    unittest.main()
