from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.causal_market_discovery import load_market_candidate_payload
from momentumbot.causal_scanner_snapshot import load_causal_scanner_snapshot
from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.indicators import completed_bar_support_series
from momentumbot.micro_bars import aggregate_trade_bars
from momentumbot.micro_execution import MicroTriggerMode
from momentumbot.micro_policy import micro_v0_1_policy
from momentumbot.micro_replay import micro_replay_runtime_artifact, replay_micro_candidate
from momentumbot.models import current_general_2026
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.providers.alpaca_trades import historical_trades
from momentumbot.research.discretion_heldout_panel import REGISTERED_DATES
from momentumbot.scanner_source_inputs import load_scanner_source_input_bundle


ET = ZoneInfo("America/New_York")
EMA_WARMUP_CALENDAR_DAYS = 7
ARTIFACT_ID = "ross-discretion-heldout-micro-date-runtime-v0.1"
SOURCE_ARTIFACT_ID = "ross-discretion-heldout-runtime-v0.1"
SOURCE_MANIFEST_CONTENT_SHA256 = (
    "2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48"
)
FROZEN_MICRO_POLICY_FINGERPRINT = (
    "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa"
)
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _validate_source_runtime(
    payload: Mapping[str, object],
    *,
    expected_content_sha256: str = SOURCE_MANIFEST_CONTENT_SHA256,
) -> None:
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported held-out runtime schema")
    if payload.get("artifact_id") != SOURCE_ARTIFACT_ID:
        raise ValueError("unexpected held-out runtime artifact")
    claimed = payload.get("content_sha256")
    projection = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if claimed != json_fingerprint(projection):
        raise ValueError("held-out runtime manifest fingerprint mismatch")
    if claimed != expected_content_sha256:
        raise ValueError("held-out runtime is not the registered frozen artifact")
    if payload.get("dates") != list(REGISTERED_DATES):
        raise ValueError("held-out runtime dates differ from registration")
    registration = payload.get("registration")
    if not isinstance(registration, Mapping):
        raise ValueError("held-out runtime lacks registration provenance")
    if registration.get("label_content_review_started") is not False:
        raise ValueError("held-out labels were opened before micro replay")
    boundary = payload.get("causal_boundary")
    if not isinstance(boundary, Mapping):
        raise ValueError("held-out runtime lacks causal boundary")
    for field in (
        "uses_benchmark_labels",
        "uses_ross_actions",
        "uses_retrospective_trade_outcomes",
        "uses_later_price_outcomes",
        "top_n_selection_applied",
    ):
        if boundary.get(field) is not False:
            raise ValueError(f"held-out runtime violates {field}")
    if boundary.get("all_market_candidates_retained") is not True:
        raise ValueError("held-out runtime omitted causal candidates")
    if boundary.get("provider_independent_scanner_replay_validated") is not True:
        raise ValueError("held-out scanner replay is not frozen")


def _utc(trading_date: date, value: time) -> pd.Timestamp:
    return pd.Timestamp(
        datetime.combine(trading_date, value, ET).astimezone(timezone.utc)
    )


def _qualification_anchor(
    candidate: Mapping[str, object],
    *,
    trading_date: date,
    session_start: time,
    entry_cutoff: time,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    bar_started_at = pd.Timestamp(candidate["first_market_qualified_bar_started_at"])
    qualified_at = pd.Timestamp(candidate["first_market_qualified_at"])
    if bar_started_at.tzinfo is None or qualified_at.tzinfo is None:
        raise ValueError("candidate qualification timestamps must be timezone-aware")
    if bar_started_at != bar_started_at.floor("min"):
        raise ValueError("candidate qualification bar must align to a minute")
    if qualified_at - bar_started_at != pd.Timedelta(minutes=1):
        raise ValueError("candidate decision must equal source bar start plus one minute")
    if qualified_at < _utc(trading_date, session_start):
        raise ValueError("candidate decision precedes the strategy session")
    if qualified_at >= _utc(trading_date, entry_cutoff):
        raise ValueError("candidate decision is at or after the entry cutoff")
    return bar_started_at, qualified_at


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_deterministic_gzip_csv(frame: pd.DataFrame, path: Path) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = io.StringIO(newline="")
    frame.reset_index().to_csv(text, index=False, lineterminator="\n")
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
            zipped.write(text.getvalue().encode("utf-8"))
    return {
        "path": path.name,
        "row_count": len(frame),
        "sha256": _sha256(path),
    }


def _freeze(payload: dict[str, object]) -> dict[str, object]:
    payload["content_sha256"] = json_fingerprint(payload)
    return payload


def _causal_action_bars(
    bars: pd.DataFrame,
    *,
    qualified_at: pd.Timestamp,
    replay_end: pd.Timestamp,
    bar_interval_seconds: int,
) -> pd.DataFrame:
    """Keep only bars that become actionable inside the frozen replay window."""
    if bar_interval_seconds <= 0:
        raise ValueError("micro bar interval must be positive")
    if qualified_at.tzinfo is None or replay_end.tzinfo is None:
        raise ValueError("micro replay bounds must be timezone-aware")
    if qualified_at >= replay_end:
        raise ValueError("micro replay start must precede its end")
    available_at = bars.index + pd.Timedelta(seconds=bar_interval_seconds)
    return bars.loc[(bars.index >= qualified_at) & (available_at < replay_end)]


def _unavailable_runtime(
    *,
    symbol: str,
    trading_date: date,
    qualified_at: pd.Timestamp,
    reason: str,
    policy_id: str,
    policy_fingerprint: str,
    source_hashes: Mapping[str, str],
) -> dict[str, object]:
    return _freeze(
        {
            "artifact_type": "micro_candidate_runtime_replay_unavailable",
            "schema_version": 1,
            "symbol": symbol,
            "trading_date": trading_date.isoformat(),
            "candidate_qualified_at": qualified_at.isoformat(),
            "status": reason,
            "plan_count": None,
            "filled_count": None,
            "frozen_policy_id": policy_id,
            "frozen_policy_fingerprint": policy_fingerprint,
            "source_hashes": dict(sorted(source_hashes.items())),
            "knowledge_policy": {
                "uses_ross_actions": False,
                "uses_benchmark_labels": False,
                "uses_retrospective_trade_outcomes": False,
                "uses_later_price_outcomes": False,
            },
            "policy_promotion_eligible": False,
        }
    )


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay frozen Micro v0.1 for every causal candidate on one registered "
            "held-out date. This program accepts no Ross labels or outcomes."
        )
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_root = args.runtime_root
    source_manifest = _read_json(source_root / "heldout-runtime-manifest.json")
    _validate_source_runtime(source_manifest)
    value = args.trading_date
    if value not in REGISTERED_DATES:
        raise ValueError("trading date is not in the registered held-out panel")
    trading_date = date.fromisoformat(value)
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    args.output.mkdir(parents=True)

    profile = current_general_2026()
    policy = micro_v0_1_policy()
    if policy.fingerprint != FROZEN_MICRO_POLICY_FINGERPRINT:
        raise RuntimeError("Micro v0.1 differs from its registered frozen fingerprint")
    market_root = source_root / "causal-market-discovery-v0.2" / value
    scanner_root = source_root / "causal-scanner-snapshot-v0.1" / value
    source_inputs_root = source_root / "causal-scanner-source-inputs-v0.1" / value
    candidates, candidate_payload, _ = load_market_candidate_payload(market_root)
    source_inputs, source_input_manifest = load_scanner_source_input_bundle(
        source_inputs_root, profile=profile
    )
    scanner_rows, scanner_payload, _ = load_causal_scanner_snapshot(
        scanner_root,
        candidate_rows=candidates,
        profile=profile,
        expected_source_hashes=source_inputs.source_hashes,
    )
    symbols = sorted(str(row["symbol"]) for row in candidates)
    if symbols != list(source_inputs.candidate_symbols):
        raise RuntimeError("candidate symbols differ from frozen scanner sidecar")
    if {str(row["symbol"]) for row in scanner_rows} != set(symbols):
        raise RuntimeError("scanner rows do not cover every held-out candidate")
    for symbol in symbols:
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError(f"unsafe candidate symbol: {symbol!r}")

    session_fetch_start = _utc(trading_date, time(4, 0))
    strategy_start = _utc(trading_date, profile.session_start)
    replay_end = _utc(trading_date, profile.no_new_entries_after)
    warmup_start = session_fetch_start - pd.Timedelta(days=EMA_WARMUP_CALENDAR_DAYS)
    client = AlpacaDataClient.from_env()
    session_frames = client.bars(
        symbols,
        timeframe="1Min",
        start=session_fetch_start.to_pydatetime(),
        end=replay_end.to_pydatetime(),
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )
    warmup_frames = client.bars(
        symbols,
        timeframe="1Min",
        start=warmup_start.to_pydatetime(),
        end=session_fetch_start.to_pydatetime(),
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )

    source_hashes = {
        "heldout_runtime": str(source_manifest["content_sha256"]),
        "market_candidates": str(candidate_payload["content_sha256"]),
        "scanner_records": str(scanner_payload["content_sha256"]),
        "scanner_source_inputs": str(source_input_manifest["content_sha256"]),
    }
    results: dict[str, object] = {}
    total_plans = 0
    total_fills = 0
    replayed_count = 0
    unavailable_count = 0

    for candidate in sorted(candidates, key=lambda row: str(row["symbol"])):
        symbol = str(candidate["symbol"])
        _, qualified_at = _qualification_anchor(
            candidate,
            trading_date=trading_date,
            session_start=profile.session_start,
            entry_cutoff=profile.no_new_entries_after,
        )
        if qualified_at < strategy_start:
            raise AssertionError("qualification anchor validation disagrees")
        symbol_root = args.output / symbol
        symbol_root.mkdir()
        session = session_frames.get(symbol, pd.DataFrame())
        warmup = warmup_frames.get(symbol, pd.DataFrame())
        if not session.empty:
            session = session.loc[
                (session.index >= session_fetch_start) & (session.index < replay_end)
            ]
        if not warmup.empty:
            warmup = warmup.loc[warmup.index < session_fetch_start]

        if session.empty:
            runtime = _unavailable_runtime(
                symbol=symbol,
                trading_date=trading_date,
                qualified_at=qualified_at,
                reason="missing_current_session_minute_support_input",
                policy_id=policy.policy_id,
                policy_fingerprint=policy.fingerprint,
                source_hashes=source_hashes,
            )
            unavailable_count += 1
        else:
            support = completed_bar_support_series(
                session,
                ema_span=profile.ema_span,
                bar_duration="1min",
                ema_warmup=warmup,
            )
            trades = historical_trades(
                client,
                symbol,
                start=qualified_at.to_pydatetime(),
                end=replay_end.to_pydatetime(),
                feed="sip",
                asof=trading_date,
            )
            if trades.empty:
                runtime = _unavailable_runtime(
                    symbol=symbol,
                    trading_date=trading_date,
                    qualified_at=qualified_at,
                    reason="no_sip_trades_after_candidate_activation",
                    policy_id=policy.policy_id,
                    policy_fingerprint=policy.fingerprint,
                    source_hashes=source_hashes,
                )
                unavailable_count += 1
            else:
                bars = aggregate_trade_bars(
                    trades, f"{policy.micro_bar_interval_seconds}s"
                )
                action_bars = _causal_action_bars(
                    bars,
                    qualified_at=qualified_at,
                    replay_end=replay_end,
                    bar_interval_seconds=policy.micro_bar_interval_seconds,
                )
                if action_bars.empty:
                    runtime = _unavailable_runtime(
                        symbol=symbol,
                        trading_date=trading_date,
                        qualified_at=qualified_at,
                        reason="no_completed_micro_bar_after_candidate_activation",
                        policy_id=policy.policy_id,
                        policy_fingerprint=policy.fingerprint,
                        source_hashes=source_hashes,
                    )
                    unavailable_count += 1
                else:
                    input_files = {
                        "trades": _write_deterministic_gzip_csv(
                            trades, symbol_root / "trades.csv.gz"
                        ),
                        "bars_10s": _write_deterministic_gzip_csv(
                            action_bars, symbol_root / "bars-10s.csv.gz"
                        ),
                        "support": _write_deterministic_gzip_csv(
                            support, symbol_root / "support-available.csv.gz"
                        ),
                        "session_1m": _write_deterministic_gzip_csv(
                            session, symbol_root / "session-1m.csv.gz"
                        ),
                        "ema_warmup_1m": _write_deterministic_gzip_csv(
                            warmup, symbol_root / "ema-warmup-1m.csv.gz"
                        ),
                    }
                    replay = replay_micro_candidate(
                        symbol,
                        action_bars,
                        trades,
                        candidate_qualified_at=qualified_at,
                        policy=policy.setup,
                        vwap_available=support["vwap"],
                        ema9_available=support["ema"],
                        trigger_mode=MicroTriggerMode.CHART_PRICE,
                        entry_latency_ms=0.0,
                        exit_until=replay_end,
                    )
                    runtime = micro_replay_runtime_artifact(replay)
                    runtime.update(
                        {
                            "trading_date": value,
                            "candidate_anchor_source": (
                                "frozen_causal_market_discovery_completed_bar_decision"
                            ),
                            "frozen_policy_id": policy.policy_id,
                            "frozen_policy_fingerprint": policy.fingerprint,
                            "frozen_policy_status": policy.status,
                            "source_hashes": dict(sorted(source_hashes.items())),
                            "replay_window_policy": (
                                "candidate_activation_to_no_new_entries_after"
                            ),
                            "replay_end": replay_end.isoformat(),
                            "input_files": input_files,
                            "retrospective_behavior_labels_loaded": False,
                            "policy_promotion_eligible": False,
                        }
                    )
                    _freeze(runtime)
                    replayed_count += 1
                    total_plans += replay.plan_count
                    total_fills += replay.filled_count

        _write_json(symbol_root / "runtime-replay.json", runtime)
        results[symbol] = {
            "status": (
                "replayed"
                if runtime["artifact_type"] == "micro_candidate_runtime_replay"
                else str(runtime["status"])
            ),
            "candidate_qualified_at": qualified_at.isoformat(),
            "plan_count": runtime.get("plan_count"),
            "filled_count": runtime.get("filled_count"),
            "runtime_content_sha256": runtime["content_sha256"],
        }

    manifest = _freeze(
        {
            "schema_version": 1,
            "artifact_id": ARTIFACT_ID,
            "trading_date": value,
            "source_heldout_runtime_content_sha256": source_manifest[
                "content_sha256"
            ],
            "frozen_micro_policy": {
                "policy_id": policy.policy_id,
                "fingerprint": policy.fingerprint,
                "status": policy.status,
            },
            "candidate_count": len(candidates),
            "replayed_candidate_count": replayed_count,
            "unavailable_candidate_count": unavailable_count,
            "total_plan_count": total_plans,
            "total_filled_count": total_fills,
            "candidate_results": results,
            "knowledge_policy": {
                "uses_ross_actions": False,
                "uses_benchmark_labels": False,
                "uses_retrospective_trade_outcomes": False,
                "uses_later_price_outcomes": False,
                "all_causal_market_candidates_retained": True,
            },
            "eligibility": {
                "activity_density_descriptive_only": True,
                "technical_rule_retuning_allowed": False,
                "policy_promotion_eligible": False,
                "full_imitation_claim_eligible": False,
            },
            "limits": [
                "entry latency is fixed at zero milliseconds",
                "Level 2 and synchronized order-book state are absent",
                "provider dissemination latency is not modeled",
            ],
        }
    )
    _write_json(args.output / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
