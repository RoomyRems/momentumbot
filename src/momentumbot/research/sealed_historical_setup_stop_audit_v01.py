"""Reconstruct existing causal setup evidence without running an account."""
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, time
from decimal import Decimal, localcontext
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import zipfile

import pandas as pd

from momentumbot import indicators, micro_bars, micro_execution, micro_setup
from momentumbot.micro_policy import micro_v0_1_policy
from momentumbot.micro_replay import causal_active_pullback_number
from momentumbot.research import prospective_daily_source as daily
from momentumbot.research import sealed_historical_micro_runtime_v01 as micro
from momentumbot.research import sealed_historical_loss_attribution_v01 as loss
from momentumbot.research.sealed_historical_source_checkpoint_v01 import canonical_fingerprint

ID = "sealed-historical-setup-stop-audit-v0.1"
PARENT = "a27babed52e1c2a12151be40af36a7c865f395f9"
PARENT_TREE = "67f32e01b56d874f278b86c2e0ca6bb45ef865f9"
LOSS_CONTRACT = "0a6153ad10b3a97ff13252db6176bdf01bf4c25474a2ee38bec8d5b5b49487ff"
LOSS_REPORT = "5487f89ae0002b276aee2c051446a862d58ec0afb1ec4c0a6b3fa16b5ff3a7d3"
MICRO_ROOT = "research/runtime/sealed-historical-micro-v0.1"
SCANNER_ROOT = "source/causal-scanner-source-inputs-v0.2"
BASE = f"research/data-audits/{ID}"
OWN_FILES = ("src/momentumbot/research/sealed_historical_setup_stop_audit_v01.py",
    "scripts/audit_sealed_historical_setups_stops_v01.py",
    "tests/test_sealed_historical_setup_stop_audit_v01.py")
SOURCE_CODE = tuple("src/momentumbot/" + p for p in (
    "micro_bars.py", "micro_execution.py", "micro_setup.py", "micro_policy.py",
    "micro_replay.py", "indicators.py", "research/prospective_daily_source.py",
    "research/sealed_historical_micro_runtime_v01.py"))
ARCHIVES = {
    "micro": {"artifact_id": micro.MICRO_INPUT_ARTIFACT_ID, "bytes": 243151926,
        "sha256": micro.MICRO_INPUT_ZIP_SHA256, "members": 688},
    "minutes": {"artifact_id": micro.SESSION_INPUT_ARTIFACT_ID, "bytes": 849877,
        "sha256": micro.SESSION_INPUT_ZIP_SHA256, "members": 348},
    "scanner": {"artifact_id": 9993250947, "bytes": 78404172,
        "sha256": "af89836213a905a1e02dabd54cce1d2bab2f55214c2d7bc0dce44d4700243638"},
}
DEFINITIONS = {
    "question": "do original causal prefixes, setup plans and stops reproduce; what explicit characteristics do all fixed entries have",
    "scope": "post-result descriptive audit; baseline losses and GITS ordinal-5 example already known",
    "selection": "all 109 original opportunities and all 744 original path decisions, including all unavailable references",
    "source_prefix": "exact original completed Micro bars, support through plan and chart trades through trigger; original prefix hash must match",
    "geometry": "unchanged Micro-v0.1 evaluator; unchanged source qualification, tick, pullback stop, volume and support",
    "ordinal": "exact original running-high pullback ordinal; descriptive, no first-N filter installed",
    "room_to_peak_r": "(original running peak - planned trigger)/(planned trigger - original stop); signed, not clipped",
    "macd": "descriptive completed-minute 12/26/9 MACD using the original raw session and normalized prior warmup; no MACD gate installed",
    "source_alignment": "original SIP trigger print versus original XNAS decision reference; receipt clocks retained separately, no consolidated-quote inference",
    "outcome_join": "saved outcomes joined only after all source prefixes verify; per-path totals remain identical",
    "no_counterfactual": "no dropped-entry profits, best thresholds, altered fills or causal policy-effect claims",
    "witness_limit": "saved geometry witnesses reproduce plans/features; full chart-prefix hash reproduction requires original source archives",
}
BOUNDARY = {**loss.BOUNDARY, "setup_policy_changed": False,
    "account_replay_executed": False, "source_prefix_reconstruction_only": True,
    "future_prices_used_for_setup": False, "counterfactual_entries_simulated": False,
    "full_quote_or_execution_model_calibrated": False}
require, seal, encoded = loss.require, loss.seal, loss.encoded
accepted = loss.baseline.accepted
money, ratio, number = loss.money, loss.ratio, loss.number


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_object(raw):
    return json.loads(raw, object_pairs_hook=accepted.unique_object)


def registration(root):
    loss.check_registration(root, LOSS_CONTRACT)
    loss.baseline.evidence.document((root / f"research/data-audits/{loss.ID}/report.json").read_bytes(), LOSS_REPORT)
    inputs = [f"research/strategy/{loss.ID}.json", f"research/data-audits/{loss.ID}/report.json",
        f"{MICRO_ROOT}/manifest.json", *[f"{MICRO_ROOT}/dates/{d}.json" for d in loss.baseline.DATES]]
    return seal({"contract_id": ID, "artifact_type": "post_result_setup_stop_audit_registration",
        "parent_commit_sha": PARENT, "parent_tree_sha": PARENT_TREE,
        "parent_loss_contract_sha256": LOSS_CONTRACT, "parent_loss_report_sha256": LOSS_REPORT,
        "definitions": DEFINITIONS, "original_archives": ARCHIVES,
        "selected_dates": list(loss.baseline.DATES), "baseline_outcomes_known_before_registration": True,
        "original_source_code_specs": {p: accepted.file_spec(root / p) for p in SOURCE_CODE},
        "input_file_specs": {p: accepted.file_spec(root / p) for p in inputs},
        "implementation_file_specs": {p: accepted.file_spec(root / p) for p in OWN_FILES}, **BOUNDARY})


def check_registration(root, expected):
    value = registration(root)
    require(value["content_sha256"] == expected, "external setup audit commitment differs")
    require((root / f"research/strategy/{ID}.json").read_bytes() == encoded(value), "setup audit registration differs")
    return value


class SourceArchive:
    """Whole original ZIP identity before any member can become audit evidence."""
    def __init__(self, path, spec):
        require(path.is_file() and not path.is_symlink(), "regular original archive required")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        require(path.stat().st_size == spec["bytes"] and digest == spec["sha256"], "original archive bytes differ")
        self.archive = zipfile.ZipFile(path)
        names = self.archive.namelist()
        require(len(set(names)) == len(names) and all(not p.startswith("/") and ".." not in Path(p).parts for p in names),
            "unsafe or repeated archive member")
        require("members" not in spec or len(names) == spec["members"], "original archive inventory differs")
        require(self.archive.testzip() is None, "original archive CRC differs")
        self.spec = spec

    def close(self):
        self.archive.close()

    def read(self, name):
        return self.archive.read(name)


class Capture(SourceArchive):
    def __init__(self, path, key):
        super().__init__(path, ARCHIVES[key])
        raw = self.read("capture-report.json")
        inv = self.read("capture-inventory.json")
        if key == "micro":
            expected = (micro.MICRO_INPUT_REPORT_FILE_SHA256, micro.MICRO_INPUT_REPORT_CONTENT_SHA256,
                micro.MICRO_INPUT_INVENTORY_FILE_SHA256, micro.MICRO_INPUT_INVENTORY_CONTENT_SHA256, 340, 2264)
        else:
            expected = (micro.SESSION_INPUT_REPORT_FILE_SHA256, micro.SESSION_INPUT_REPORT_CONTENT_SHA256,
                micro.SESSION_INPUT_INVENTORY_FILE_SHA256, micro.SESSION_INPUT_INVENTORY_CONTENT_SHA256, 170, 170)
        require(sha(raw) == expected[0] and sha(inv) == expected[2], "original capture metadata bytes differ")
        report, inventory = json_object(raw), json_object(inv)
        require(report["content_sha256"] == expected[1] and inventory["content_sha256"] == expected[3], "capture identity differs")
        require(report["status"] == "complete" and report["logical_requests_completed"] == expected[4]
            and inventory["complete"] and inventory["provider_attempts"] == expected[5] and inventory["blocked_attempts"] == 0,
            "original capture incomplete")
        require(set(inventory["files"]) == set(self.archive.namelist()) - {"capture-inventory.json"}, "capture file inventory differs")
        for name, digest in inventory["files"].items():
            require(sha(self.read(name)) == digest, "capture member bytes differ")
        self.receipts = {r["path"]: r for r in report["receipts"]}
        require(len(self.receipts) == expected[4], "capture receipts repeat")
        self.requests = {r["request_id"]: r for r in json_object(self.read("requests.json"))["requests"]}

    def tape(self, day, symbol, kind):
        path = f"dates/{day}/{symbol}-{kind}.jsonl.gz"
        receipt = self.receipts[path]
        raw = self.read(path)
        require(receipt["complete"] and receipt["file_sha256"] == sha(raw), "incomplete or altered input tape")
        decoded = gzip.decompress(raw)
        require(sha(decoded) == receipt["logical_sha256"], "uncompressed source hash differs")
        rows = [json_object(line) for line in decoded.splitlines()]
        require(len(rows) == receipt["record_count"] and rows, "source tape count differs")
        request = self.requests[receipt["request_id"]]
        require(request["symbol"] == symbol and request["trading_date"] == day and request["kind"] == kind,
            "source request identity differs")
        stamps = pd.to_datetime([r["t"] for r in rows], format="ISO8601", utc=True)
        require(stamps.is_monotonic_increasing and stamps[0] >= pd.Timestamp(request["start_inclusive"])
            and stamps[-1] < pd.Timestamp(request["end_exclusive"]), "source clock outside original request")
        if kind == "sip_trades":
            values = {"price": [r["p"] for r in rows], "size": [r["s"] for r in rows],
                "conditions": [r["c"] for r in rows], "tape": [r["z"] for r in rows]}
        else:
            values = {col: [r[key] for r in rows] for col, key in
                (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"), ("volume", "v"), ("vwap", "vw"))}
        return pd.DataFrame(values, index=stamps), {"request": request, "receipt": receipt}


def scanner_frames(archive, day, symbols):
    """Select only raw/split pairs; whole original archive and stream remain pinned."""
    prefix = f"{SCANNER_ROOT}/{day}"
    manifest = json_object(archive.read(f"{prefix}/manifest.json"))
    compressed = archive.read(f"{prefix}/market-inputs.jsonl.gz")
    require(sha(compressed) == manifest["summary"]["compressed_file_sha256"], "scanner compressed stream differs")
    logical = gzip.decompress(compressed)
    require(sha(logical) == manifest["summary"]["logical_records_sha256"], "scanner logical stream differs")
    selected, counts = defaultdict(list), Counter()
    for line in logical.splitlines():
        kind, raw = line.split(b"\t", 1)
        counts[kind.decode()] += 1
        if kind not in (b"candidate_raw_bar", b"rank_split_close_bar"):
            continue
        row = json_object(raw)
        if row["symbol"] in symbols:
            selected[(row["symbol"], kind)].append(row)
    require(dict(counts) == manifest["summary"]["record_counts"], "scanner record counts differ")
    out = {}
    for symbol in sorted(symbols):
        raw, split = selected[(symbol, b"candidate_raw_bar")], selected[(symbol, b"rank_split_close_bar")]
        a = pd.DataFrame({"close": [r["raw_close"] for r in raw], "volume": [r["raw_volume"] for r in raw]},
            index=pd.to_datetime([r["bar_started_at"] for r in raw], utc=True))
        b = pd.Series([r["split_adjusted_close"] for r in split], index=pd.to_datetime([r["bar_started_at"] for r in split], utc=True))
        require(a.index.equals(b.index) and a.index.is_unique and a.index.is_monotonic_increasing, "raw/split source clocks differ")
        out[symbol] = (a, b)
    return out, {"manifest_content_sha256": manifest["content_sha256"], "stream_sha256": sha(logical), "record_counts": dict(counts)}


@lru_cache(maxsize=512)
def eligibility(tape, conditions):
    return micro_bars.minute_trade_eligibility(tape, conditions)


def aggregate_source(trades):
    """Column iteration of the frozen aggregation arithmetic; original policy unchanged.

    Preserve row order, additions, timestamp ties and all original output columns.
    Every real causal prefix must independently match the pre-existing hash.
    """
    if trades.empty:
        return micro_bars._empty_bars()
    ordered = trades.sort_index()
    buckets = {}
    for stamp, price, size, conditions, tape in ordered.itertuples(index=True, name=None):
        bucket = stamp.value // 10_000_000_000 * 10_000_000_000
        state = buckets.setdefault(bucket, {"open": None, "high": None, "low": None, "close": None,
            "volume": 0, "trade_count": 0, "vwap_numerator": 0.0, "vwap_volume": 0,
            "unknown_conditions": set(), "open_time": None, "high_time": None, "low_time": None, "close_time": None})
        rule = eligibility(tape, tuple(conditions or ()))
        state["unknown_conditions"].update(rule.unknown_conditions)
        price, size = float(price), int(size)
        if rule.updates_volume:
            state["volume"] += size
            state["trade_count"] += 1
        if not rule.updates_price:
            continue
        if state["open"] is None:
            state["open"], state["open_time"] = price, stamp
        if state["high"] is None or price > state["high"]:
            state["high"], state["high_time"] = price, stamp
        if state["low"] is None or price < state["low"]:
            state["low"], state["low_time"] = price, stamp
        state["close"], state["close_time"] = price, stamp
        if rule.updates_volume:
            state["vwap_numerator"] += price * size
            state["vwap_volume"] += size
    rows, index = [], []
    for bucket, s in sorted(buckets.items()):
        if s["open"] is None or s["volume"] <= 0:
            continue
        rows.append({k: s[k] for k in ("open", "high", "low", "close", "volume", "trade_count")}
            | {"vwap": s["vwap_numerator"] / s["vwap_volume"] if s["vwap_volume"] else float("nan")}
            | {k: s[k] for k in ("open_time", "high_time", "low_time", "close_time")}
            | {"unknown_condition_count": len(s["unknown_conditions"])})
        index.append(pd.Timestamp(bucket, unit="ns", tz=trades.index.tz))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index, name="timestamp")) if rows else micro_bars._empty_bars()


def chart_source(trades):
    if trades.empty:
        return micro_execution.price_eligible_trades(trades)
    ordered = trades.copy()
    ordered["_source_sequence"] = range(len(ordered))
    ordered = ordered.sort_index(kind="stable")
    keep = [eligibility(str(t or ""), micro_execution._conditions(c)).updates_price
        for t, c in zip(ordered["tape"], ordered["conditions"])]
    ordered["_execution_via_odd_lot"] = False
    result = ordered.loc[keep].copy()
    result["_sequence"] = range(len(result))
    return result


def frame_payload(frame, through):
    """Equivalent mixed-frame serialization, with numeric row coercion retained."""
    selected = frame.loc[:through]
    # Frozen support frames contain homogeneous numeric values. Micro/chart
    # frames have object fields, so iterrows never coerces their ints to floats.
    numeric = all(pd.api.types.is_numeric_dtype(t) for t in selected.dtypes)
    if numeric:
        return daily._frame_prefix(frame, through=through)
    columns = list(selected.columns)
    return [{"timestamp": pd.Timestamp(values[0]).isoformat(),
        **{str(k): daily._json_value(v) for k, v in zip(columns, values[1:])}}
        for values in selected.itertuples(index=True, name=None)]


def plan_payload(plan, ordinal):
    return {"symbol": plan.symbol, **{k: getattr(plan, k).isoformat() for k in ("source_bar_start", "armed_at", "expires_at")},
        **{k: getattr(plan, k) for k in ("breakout_level", "minimum_new_high_price", "stop_price")}, "pullback_number": ordinal}


def evaluate_geometry(decision, bars, support):
    plan = decision["plan"]
    qualified, start = pd.Timestamp(decision["candidate_qualified_at"]), pd.Timestamp(plan["source_bar_start"])
    prefix = bars.loc[(bars.index >= qualified) & (bars.index <= start)]
    require(len(prefix) and prefix.index[-1] == start and start + pd.Timedelta(seconds=10) == pd.Timestamp(plan["armed_at"]),
        "completed plan bar or arm clock differs")
    ordinal = causal_active_pullback_number(prefix, candidate_qualified_at=qualified)
    evaluation = micro_setup.evaluate_micro_pullback_plan(decision["symbol"], prefix,
        candidate_qualified_at=qualified, policy=micro_v0_1_policy().setup,
        pullback_number=ordinal, vwap_available=support["vwap"], ema9_available=support["ema"])
    require(evaluation.plan is not None and plan_payload(evaluation.plan, ordinal) == plan, "original geometry, ordinal or stop differs")
    features = daily._json_value(asdict(evaluation.features))
    trough = pd.Timestamp(features["trough_time"])
    available = support.loc[:trough]
    require(not available.empty and available.index[-1] <= trough <= start, "support unavailable at original trough")
    return prefix, features, available.index[-1]


def signed_ratio(top, bottom):
    return None if bottom <= 0 else ratio(top, bottom)


def descriptive_fields(decision, features, support_at, macd_values):
    p = decision["plan"]
    start = pd.Timestamp(p["source_bar_start"])
    available = macd_values.loc[:start]
    macd_row = available.iloc[-1] if len(available) else None
    with localcontext() as ctx:
        ctx.prec = 60
        risk = Decimal(str(p["minimum_new_high_price"])) - Decimal(str(p["stop_price"]))
        require(risk > 0, "original planned risk is nonpositive")
        room = Decimal(str(features["peak_high"])) - Decimal(str(p["minimum_new_high_price"]))
        macd_out = None if macd_row is None else {k: None if not math.isfinite(float(v)) else str(float(v)) for k, v in macd_row.items()}
        return {"features": features, "planned_risk_per_share_usd": money(risk),
            "room_to_original_peak_r": signed_ratio(room, risk), "room_below_2r": room < 2 * risk,
            "support_available_at": support_at.isoformat(), "completed_minute_macd": macd_out,
            "macd_available_at": None if macd_row is None else available.index[-1].isoformat(),
            "macd_line_nonpositive": None if not macd_out or macd_out["macd"] is None else Decimal(macd_out["macd"]) <= 0}


def reconstruct_decision(source, bars, chart, support, macd_values):
    decision = source["source_decision"]
    prefix, features, support_at = evaluate_geometry(decision, bars, support)
    p = decision["plan"]
    start, qualified, at = (pd.Timestamp(x) for x in (p["source_bar_start"], decision["candidate_qualified_at"], decision["decision_at"]))
    end = pd.Timestamp(datetime.combine(at.date(), time(10), micro.ET))
    window = chart.loc[(chart.index >= pd.Timestamp(p["armed_at"])) & (chart.index < pd.Timestamp(p["expires_at"])) & (chart.index < end)]
    crossing = window.loc[pd.to_numeric(window["price"]) >= p["minimum_new_high_price"]]
    require(not crossing.empty and crossing.index[0] == at, "first causal chart crossing differs")
    trigger = crossing.iloc[0]
    payload = {"activation_id": decision["activation_id"], "candidate_qualified_at": decision["candidate_qualified_at"],
        "policy_fingerprint": micro_v0_1_policy().fingerprint, "plan_id": decision["plan_id"], "plan": p,
        "micro_bars_through_plan": frame_payload(prefix, start), "support_through_plan": frame_payload(support, start),
        "chart_trades_through_trigger": frame_payload(chart.loc[chart.index >= qualified], at), "decision_at": decision["decision_at"]}
    digest = canonical_fingerprint(payload)
    require(digest == decision["micro_runtime_content_sha256"], "original causal prefix hash differs")
    return {"opportunity_id": source["opportunity_id"], "symbol": decision["symbol"],
        "trading_date": source["window"]["opportunity"]["trading_date"], "activation_id": decision["activation_id"],
        "source_decision": decision, "original_prefix_sha256": digest, "original_prefix_matches": True,
        **descriptive_fields(decision, features, support_at, macd_values),
        "trigger": {"timestamp": at.isoformat(), "price": str(float(trigger["price"])),
            "size": int(trigger["size"]), "conditions": daily._json_value(trigger["conditions"]),
            "tape": str(trigger["tape"]), "original_source_ordinal": int(trigger["_source_sequence"]),
            "chart_sequence": int(trigger["_sequence"])},
        "original_input_status": source["entry"]["input_status"], "original_input_reason": source["entry"]["reason"]}


def alignment(row, reference):
    if reference is None:
        require(row["original_input_status"] == "unavailable", "available input lost its reference")
        return None
    require(row["original_input_status"] == "available", "unavailable input gained a reference")
    with localcontext() as ctx:
        ctx.prec = 60
        plan = row["source_decision"]["plan"]
        ask, bid, stop, trigger = (Decimal(str(x)) for x in
            (reference["ask_price"], reference["bid_price"], plan["stop_price"], row["trigger"]["price"]))
        at = loss.baseline.timestamp_ns(row["source_decision"]["decision_at"])
        age = at - reference["ts_recv_ns"]
        require(0 <= age <= 100_000_000 and bid < ask, "original decision reference clock/spread differs")
        return {"original_reference": reference, "quote_age_ns": age, "spread_usd": money(ask - bid),
            "ask_to_stop_usd": money(ask - stop), "spread_over_ask_stop_distance": signed_ratio(ask - bid, ask - stop),
            "ask_minus_sip_trigger_usd": money(ask - trigger), "sip_exchange_time_and_xnas_receive_time_are_distinct": True,
            "standing_or_consolidated_quote_inferred": False}


def original_evidence(root):
    previous = loss.baseline.evidence.document((root / f"research/data-audits/{loss.ID}/report.json").read_bytes(), LOSS_REPORT)
    require(loss.analyze(root, LOSS_CONTRACT) == previous, "original loss report no longer reproduces")
    original = accepted.verified_zip(root / f"{loss.baseline.BASE}/source-binding-original.zip", accepted.ARCHIVES["binding"])
    binding = accepted.read_json(original["source-bindings.json"])
    observations = loss.baseline.evidence.document((root / loss.baseline.OBSERVATIONS).read_bytes(), loss.baseline.EVIDENCE_RESULT)
    refs = loss.decision_references(root, {r["opportunity_id"]: r for r in observations["rows"]})
    return previous, binding, refs


def join_paths(previous, rows):
    lookup = {r["opportunity_id"]: r for r in rows}
    require(len(lookup) == len(rows) == 109, "setup population differs")
    results = []
    with localcontext() as ctx:
        ctx.prec = 60
        for path in previous["paths"]:
            groups = defaultdict(list)
            entries = []
            for e in path["episodes"]:
                row = lookup[e["opportunity_id"]]
                p = row["source_decision"]["plan"]
                require(Decimal(e["initial_stop_usd"]) == Decimal(str(p["stop_price"]))
                    and row["quote_alignment"] is not None, "saved entry stop differs from reconstructed source")
                ask = Decimal(str(row["quote_alignment"]["original_reference"]["ask_price"]))
                require(Decimal(e["decision_ask_usd"]) == ask, "saved entry reference differs")
                record = {"entry_fill_id": e["entry_fill_id"], "opportunity_id": e["opportunity_id"],
                    "pullback_number": p["pullback_number"], "original_stop_matches": True,
                    "actual_entry_to_stop_usd": money(Decimal(e["entry_price_usd"]) - Decimal(e["initial_stop_usd"])),
                    "net_pnl_usd": e["net_pnl_usd"], "original_entry_quantity": e["entry_quantity"],
                    "room_below_2r": row["room_below_2r"], "macd_line_nonpositive": row["macd_line_nonpositive"]}
                entries.append(record)
                groups[p["pullback_number"]].append(e)
            cohorts = [{"pullback_number": n, "closed_episodes": len(es),
                "net_pnl_usd": money(sum((Decimal(e["net_pnl_usd"]) for e in es), Decimal(0)))} for n, es in sorted(groups.items())]
            total = sum((Decimal(e["net_pnl_usd"]) for e in entries), Decimal(0))
            require(total == Decimal(path["totals"]["net_pnl_usd"]), "ordinal cohorts do not reconcile")
            for d in path["decisions"]:
                require(d["opportunity_id"] in lookup and d["input_status"] == lookup[d["opportunity_id"]]["original_input_status"],
                    "original decision population or availability changed")
            results.append({"path_id": path["path_id"], "account_key": path["account_key"],
                "horizon_seconds": path["horizon_seconds"], "scenario_id": path["scenario_id"],
                "original_totals": path["totals"], "original_disposition_counts": path["original_disposition_counts"],
                "original_decisions": path["decisions"], "original_exit_reasons": path["exit_reasons"],
                "entries": entries, "exact_ordinal_cohorts": cohorts,
                "entries_with_room_below_2r": sum(e["room_below_2r"] for e in entries),
                "entries_with_nonpositive_macd": sum(e["macd_line_nonpositive"] is True for e in entries),
                "entries_with_unknown_macd": sum(e["macd_line_nonpositive"] is None for e in entries)})
    require(len(results) == 12 and sum(len(p["entries"]) for p in results) == 300
        and sum(len(p["original_decisions"]) for p in results) == 744, "original path/entry/decision counts differ")
    return results


def pack_frame(frame, through):
    selected = frame.loc[:through]
    require(all(pd.api.types.is_numeric_dtype(t) for t in selected.dtypes), "numeric geometry witness required")
    return {"columns": list(selected.columns), "rows": [[pd.Timestamp(v[0]).isoformat(), *[None if pd.isna(x) else daily._json_value(x) for x in v[1:]]]
        for v in selected.itertuples(index=True, name=None)]}


def unpack_frame(value):
    rows = value["rows"]
    result = pd.DataFrame([r[1:] for r in rows], columns=value["columns"], index=pd.to_datetime([r[0] for r in rows], utc=True))
    require(result.index.is_unique and result.index.is_monotonic_increasing, "geometry witness clocks repeat or reverse")
    return result.apply(pd.to_numeric, errors="raise")


def report_payload(previous, expected, witness, metadata, rows):
    return seal({"contract_id": ID, "artifact_type": "causal_setup_stop_source_audit",
        "contract_content_sha256": expected, "parent_loss_report_sha256": LOSS_REPORT,
        "runtime_content_sha256": previous["runtime_content_sha256"], "selected_dates": list(loss.baseline.DATES),
        "original_archives": ARCHIVES, "source_pairs": metadata,
        "witness_content_sha256": witness["content_sha256"], "definitions": DEFINITIONS,
        "population": previous["population"], "opportunities": rows, "paths": join_paths(previous, rows),
        "all_109_original_prefixes_match": len(rows) == 109 and all(r["original_prefix_matches"] for r in rows),
        "all_300_original_stops_match": True, "all_account_results_unchanged": True,
        "ordinal_counts": dict(sorted(Counter(str(r["features"]["pullback_number"]) for r in rows).items(), key=lambda x: int(x[0]))),
        "opportunities_with_room_below_2r": sum(r["room_below_2r"] for r in rows),
        "opportunities_with_nonpositive_macd": sum(r["macd_line_nonpositive"] is True for r in rows),
        "opportunities_with_unknown_macd": sum(r["macd_line_nonpositive"] is None for r in rows), **BOUNDARY})


def build(root, expected, paths, progress=lambda message: None):
    check_registration(root, expected)
    previous, binding, refs = original_evidence(root)
    groups = defaultdict(list)
    for source in binding["opportunities"]:
        d = source["source_decision"]
        groups[(source["window"]["opportunity"]["trading_date"], d["symbol"])].append(source)
    sources = {}
    try:
        sources["micro"] = Capture(paths["micro"], "micro")
        sources["minutes"] = Capture(paths["minutes"], "minutes")
        sources["scanner"] = SourceArchive(paths["scanner"], ARCHIVES["scanner"])
        progress("All three original archives and capture inventories verified")
        rows, witnesses, metadata = [], {}, []
        cache_day, cache_frames, scanner_meta = None, None, None
        for ordinal, ((day, symbol), opportunities) in enumerate(sorted(groups.items()), 1):
            if day != cache_day:
                cache_frames, scanner_meta = scanner_frames(sources["scanner"], day, {s for d, s in groups if d == day})
                cache_day = day
            raw_scanner, split = cache_frames[symbol]
            original_day = micro.frozen(root / f"{MICRO_ROOT}/dates/{day}.json")
            original_decisions = {d["plan_id"]: d for d in original_day["decisions"]}
            for s in opportunities:
                require(s["source_decision"] == original_decisions[s["source_decision"]["plan_id"]], "bound original decision differs")
            # Normalization uses the earliest original symbol activation, including
            # activations without a decision in this audit's opportunity population.
            qualified = min(pd.Timestamp(a["candidate_qualified_at"]) for a in original_day["activations"] if a["symbol"] == symbol)
            factor, basis = micro.causal_raw_to_split_factor(raw_scanner["close"], split, qualified_at=qualified)
            require(basis == original_day["basis_evidence"][symbol], "original causal raw/split basis differs")
            trades, trade_meta = sources["micro"].tape(day, symbol, "sip_trades")
            warmup, warm_meta = sources["micro"].tape(day, symbol, "ema_warmup_1m_split")
            session, session_meta = sources["minutes"].tape(day, symbol, "session_1m_raw")
            warmup = micro.normalize_warmup_to_raw(warmup, factor)
            end = pd.Timestamp(datetime.combine(date.fromisoformat(day), time(10), micro.ET))
            session = session.loc[session.index + pd.Timedelta(minutes=1) < end]
            require(session.index.equals(raw_scanner.index) and session["close"].astype(float).equals(raw_scanner["close"].astype(float))
                and session["volume"].astype(float).equals(raw_scanner["volume"].astype(float)), "raw session/scanner alignment differs")
            support = indicators.completed_bar_support_series(session, ema_warmup=warmup)
            bars, chart = aggregate_source(trades), chart_source(trades)
            macd_values = indicators.macd(indicators._ema_bars(session, warmup)["close"]).reindex(session.index)
            macd_values.index = macd_values.index + pd.Timedelta(minutes=1)
            key = day + "/" + symbol
            last = max(pd.Timestamp(o["source_decision"]["plan"]["source_bar_start"]) for o in opportunities)
            witnesses[key] = {"micro": pack_frame(bars[["open", "high", "low", "close", "volume"]], last),
                "support": pack_frame(support, last), "macd": pack_frame(macd_values, last)}
            for source in opportunities:
                row = reconstruct_decision(source, bars, chart, support, macd_values)
                row["witness_key"] = key
                row["quote_alignment"] = alignment(row, refs[row["opportunity_id"]])
                rows.append(row)
            metadata.append({"key": key, "basis": basis, "scanner": scanner_meta,
                "sip": trade_meta, "warmup": warm_meta, "session": session_meta, "opportunities_checked": len(opportunities)})
            progress(f"Verified {ordinal}/{len(groups)} source pairs: {day} {symbol}; {len(rows)} original decisions")
        indexed = {r["opportunity_id"]: r for r in rows}
        rows = [indexed[s["opportunity_id"]] for s in binding["opportunities"]]
        witness = seal({"contract_id": ID, "purpose": "saved geometry only; full prefix authentication uses original archives",
            "groups": witnesses})
        report = report_payload(previous, expected, witness, metadata, rows)
        verify_result(report, witness, expected, previous, binding, refs)
        return report, witness
    finally:
        for source in sources.values():
            source.close()


def verify_saved(root, expected):
    check_registration(root, expected)
    report = accepted.read_json((root / BASE / "report.json").read_bytes())
    witness = accepted.read_json(gzip.decompress((root / BASE / "geometry-witnesses.json.gz").read_bytes()))
    previous, binding, refs = original_evidence(root)
    verify_result(report, witness, expected, previous, binding, refs)
    require((root / BASE / "report.md").read_text(encoding="utf-8") == render_markdown(report), "saved Markdown differs")
    return report


def verify_result(report, witness, expected, previous, binding, refs):
    require(report["contract_content_sha256"] == expected and report["witness_content_sha256"] == witness["content_sha256"], "saved witness/report binding differs")
    require([r["opportunity_id"] for r in report["opportunities"]] == [s["opportunity_id"] for s in binding["opportunities"]], "saved opportunity order differs")
    keys = {s["window"]["opportunity"]["trading_date"] + "/" + s["source_decision"]["symbol"] for s in binding["opportunities"]}
    require(len(keys) == 45 and set(witness["groups"]) == keys and [s["key"] for s in report["source_pairs"]] == sorted(keys), "source pair population differs")
    frames = {key: {k: unpack_frame(v) for k, v in group.items()} for key, group in witness["groups"].items()}
    for row, source in zip(report["opportunities"], binding["opportunities"]):
        require(row["source_decision"] == source["source_decision"] and row["original_prefix_sha256"] == source["source_decision"]["micro_runtime_content_sha256"], "saved original identity differs")
        d = source["source_decision"]
        day = source["window"]["opportunity"]["trading_date"]
        require(row["witness_key"] == day + "/" + d["symbol"] and row["symbol"] == d["symbol"] and row["trading_date"] == day
            and row["activation_id"] == d["activation_id"] and row["original_prefix_matches"] is True
            and row["original_input_status"] == source["entry"]["input_status"] and row["original_input_reason"] == source["entry"]["reason"], "saved opportunity binding differs")
        group = frames[row["witness_key"]]
        _, features, at = evaluate_geometry(d, group["micro"], group["support"])
        fields = descriptive_fields(d, features, at, group["macd"])
        require(all(row[k] == v for k, v in fields.items()), "saved descriptive geometry or MACD differs")
        trigger = row["trigger"]
        require(trigger["timestamp"] == d["decision_at"] and Decimal(trigger["price"]) >= Decimal(str(d["plan"]["minimum_new_high_price"]))
            and trigger["original_source_ordinal"] >= trigger["chart_sequence"] >= 0
            and eligibility(trigger["tape"], tuple(trigger["conditions"])).updates_price, "saved trigger boundary differs")
        require(row["quote_alignment"] == alignment(row, refs[row["opportunity_id"]]), "saved quote alignment differs")
    require(report == report_payload(previous, expected, witness, report["source_pairs"], report["opportunities"]), "saved audit totals, cohorts or authority differ")


def render_markdown(report):
    lines = ["# Historical setup, stop and source audit v0.1", "",
        "All 109 original causal prefixes and all 300 recorded entry stops reproduce. The baseline and all original coverage flags remain unchanged.", "",
        f"Exact pullback ordinal counts: `{json.dumps(report['ordinal_counts'], sort_keys=True)}`.",
        f"{report['opportunities_with_room_below_2r']}/109 opportunities have less than 2R room to the original peak at the planned trigger. "
        f"{report['opportunities_with_nonpositive_macd']}/109 have nonpositive completed-minute MACD; "
        f"{report['opportunities_with_unknown_macd']}/109 have unknown MACD.", "",
        "These are descriptive checks on the unchanged Micro policy, not newly installed filters or proof that a filter improves returns.", "",
        "| Account | Execution | Horizon | Episodes | Net P&L | Entries with room <2R | Entries with MACD ≤0 |", "|---|---|---:|---:|---:|---:|---:|"]
    for p in report["paths"]:
        lines.append(f"| {p['account_key']} | {p['scenario_id']} | {p['horizon_seconds']} | {len(p['entries'])} | {p['original_totals']['net_pnl_usd']} | {p['entries_with_room_below_2r']} | {p['entries_with_nonpositive_macd']} |")
    lines += ["", "The complete JSON retains every opportunity, source binding, original decision, exact-ordinal cohort and path. "
        "SIP trade timestamps and single-venue quote receive timestamps are distinct clocks. No standing/consolidated quote, alternate fill or excluded-trade profit is inferred.", "",
        "Saved geometry witnesses reproduce the setup and stop. Reproducing the complete causal-prefix hash requires the three original source archives. "
        "The audit uses the accepted historical execution results; it does not re-simulate management, fills or accounts.", ""]
    return "\n".join(lines)
