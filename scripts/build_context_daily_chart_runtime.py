from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.causal_market_discovery import load_market_candidate_payload
from momentumbot.causal_scanner_snapshot import load_causal_scanner_snapshot
from momentumbot.historical_float import load_causal_float_records
from momentumbot.historical_news import (
    load_publication_timed_news,
    news_events_fingerprint,
)
from momentumbot.identity_resolved_universe import (
    identity_resolved_membership_fingerprint,
    load_identity_resolved_universe,
)
from momentumbot.models import current_general_2026
from momentumbot.providers.alpaca import AlpacaDataClient
from momentumbot.research.catalyst_evidence import build_catalyst_evidence_packets
from momentumbot.research.context_runtime import (
    DAILY_RUNTIME_ARTIFACT_ID,
    build_record_date_payload,
    build_record_root_manifest,
    load_context_runtime_request,
    load_market_runtime_manifest,
    write_json,
)
from momentumbot.research.daily_chart_context import (
    CONTRACT_ID,
    build_daily_chart_evidence,
    canonical_fingerprint,
    load_daily_chart_context_contract,
)
from momentumbot.scanner_source_inputs import load_scanner_source_input_bundle


ET = ZoneInfo("America/New_York")
IDENTITY_VERIFIED_LOOKBACK_CALENDAR_DAYS = 120


def build_daily_records_for_date(
    *,
    trading_date: str,
    scanner_rows: Iterable[Mapping[str, object]],
    catalyst_packets: Iterable[Mapping[str, object]],
    identity_rows: Iterable[Mapping[str, object]],
    split_daily_bars_by_symbol: Mapping[str, pd.DataFrame],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    target = date.fromisoformat(trading_date)
    materialized_identities = [dict(row) for row in identity_rows]
    scanner_by_key = {
        (str(row["symbol"]), str(row["decision_time"])): dict(row)
        for row in scanner_rows
    }
    identities = {str(row["ticker"]): row for row in materialized_identities}
    if len(identities) != len(materialized_identities):
        raise ValueError("identity rows repeat a ticker")
    records: list[dict[str, object]] = []
    unavailable: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for packet in catalyst_packets:
        symbol = str(packet.get("symbol") or "").strip().upper()
        decision_time = str(packet.get("decision_time") or "")
        key = (symbol, decision_time)
        if key in seen:
            raise ValueError("daily context decision keys repeat")
        seen.add(key)
        scanner = scanner_by_key.get(key)
        if scanner is None:
            raise ValueError("daily context decision lacks an exact scanner row")
        identity = identities.get(symbol)
        if identity is None:
            raise ValueError("daily context candidate lacks resolved identity")
        frame = split_daily_bars_by_symbol.get(symbol, pd.DataFrame())
        prior = frame
        if not frame.empty:
            if frame.index.tz is None:
                raise ValueError("daily context provider bars must be timezone-aware")
            prior = frame.loc[frame.index.tz_convert(ET).date < target]
        if prior.empty:
            unavailable.append(
                {
                    "symbol": symbol,
                    "decision_time": decision_time,
                    "packet_reason": packet.get("packet_reason"),
                    "reason": "no_prior_completed_split_adjusted_daily_bars",
                }
            )
            continue
        records.append(
            build_daily_chart_evidence(
                prior,
                symbol=symbol,
                decision_time=decision_time,
                decision_price=float(scanner["price"]),
                identity_identifier_kind=str(
                    identity["identity_identifier_kind"]
                ),
                identity_identifier=str(identity["identity_identifier"]),
                identity_verified_start_date=(
                    target - timedelta(days=IDENTITY_VERIFIED_LOOKBACK_CALENDAR_DAYS)
                ),
                identity_verified_through_date=target,
            )
        )
    records.sort(key=lambda row: (str(row["decision_time"]), str(row["symbol"])))
    unavailable.sort(
        key=lambda row: (str(row["decision_time"]), str(row["symbol"]))
    )
    return records, unavailable


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize causal daily-chart records for the context panel."
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asset-batch-size", type=int, default=250)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    market_manifest = load_market_runtime_manifest(args.runtime_root)
    request = load_context_runtime_request(
        "research/data-audits/context-heldout-runtime-request-v0.1.json"
    )
    if market_manifest["registration"]["request_content_sha256"] != request[
        "content_sha256"
    ]:
        raise RuntimeError("market runtime uses a different registered request")
    dates = list(market_manifest["dates"])
    contract = load_daily_chart_context_contract(
        "research/strategy/daily-chart-context-shadow-v0.1.json"
    )
    contract_hash = canonical_fingerprint(contract)
    if contract_hash != request["frozen_contracts"][
        "daily_chart_content_sha256"
    ]:
        raise RuntimeError("daily-chart contract differs from the registered request")
    client = AlpacaDataClient.from_env()
    profile = current_general_2026()
    identity_root = args.runtime_root / "identity-resolved-universe-v0.1"
    market_root = args.runtime_root / "causal-market-discovery-v0.2"
    float_root = args.runtime_root / "causal-sec-float-v0.1"
    news_root = args.runtime_root / "causal-alpaca-news-v0.2"
    scanner_root = args.runtime_root / "causal-scanner-snapshot-v0.1"
    scanner_inputs_root = args.runtime_root / "causal-scanner-source-inputs-v0.1"
    args.output.mkdir(parents=True)
    date_payloads: dict[str, dict[str, object]] = {}
    for value in dates:
        target = date.fromisoformat(value)
        identities, _, _ = load_identity_resolved_universe(
            identity_root,
            trading_date=value,
        )
        candidates, candidate_payload, _ = load_market_candidate_payload(
            market_root / value
        )
        _, float_manifest = load_causal_float_records(
            float_root / value,
            candidate_rows=candidates,
            candidate_payload=candidate_payload,
        )
        news_events, _, news_manifest = load_publication_timed_news(
            news_root / value,
            candidate_rows=candidates,
            candidate_payload=candidate_payload,
            source_float_records_sha256=str(
                float_manifest["summary"]["records_sha256"]
            ),
        )
        source_inputs, _ = load_scanner_source_input_bundle(
            scanner_inputs_root / value,
            profile=profile,
        )
        scanner_rows, scanner_payload, _ = load_causal_scanner_snapshot(
            scanner_root / value,
            candidate_rows=candidates,
            profile=profile,
            expected_source_hashes=source_inputs.source_hashes,
        )
        packets = (
            build_catalyst_evidence_packets(
                scanner_rows,
                {"full_window_event_tape": news_events},
            )
            if scanner_rows
            else []
        )
        symbols = sorted({str(packet["symbol"]) for packet in packets})
        frames = client.bars_batched(
            symbols,
            batch_size=args.asset_batch_size,
            timeframe="1Day",
            start=datetime.combine(
                target - timedelta(days=IDENTITY_VERIFIED_LOOKBACK_CALENDAR_DAYS),
                time(0),
                timezone.utc,
            ),
            end=datetime.combine(
                target + timedelta(days=1),
                time(0),
                timezone.utc,
            ),
            feed="sip",
            adjustment="split",
            asof=target,
        )
        rejected = sorted(set(symbols) & set(client.invalid_symbols))
        if rejected:
            raise RuntimeError(
                "daily context provider rejected frozen candidates: "
                + ",".join(rejected)
            )
        records, unavailable = build_daily_records_for_date(
            trading_date=value,
            scanner_rows=scanner_rows,
            catalyst_packets=packets,
            identity_rows=identities,
            split_daily_bars_by_symbol=frames,
        )
        source_hashes = {
            "market_runtime": str(market_manifest["content_sha256"]),
            "scanner_records": str(scanner_payload["content_sha256"]),
            "identity_membership": identity_resolved_membership_fingerprint(
                identities
            ),
            "publication_timed_news_events": news_events_fingerprint(news_events),
            "publication_timed_news_manifest": canonical_fingerprint(news_manifest),
        }
        payload = build_record_date_payload(
            artifact_id=DAILY_RUNTIME_ARTIFACT_ID,
            contract_id=CONTRACT_ID,
            trading_date=value,
            source_hashes=source_hashes,
            records=records,
            unavailable=unavailable,
        )
        write_json(args.output / "dates" / f"{value}.json", payload)
        date_payloads[value] = payload
    manifest = build_record_root_manifest(
        artifact_id=DAILY_RUNTIME_ARTIFACT_ID,
        contract_id=CONTRACT_ID,
        contract_content_sha256=contract_hash,
        source_market_runtime_content_sha256=str(market_manifest["content_sha256"]),
        date_payloads=date_payloads,
    )
    write_json(args.output / "manifest.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
