from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.providers.alpaca import AlpacaDataClient

ET = ZoneInfo("America/New_York")
FLOAT_LIMIT = 10_000_000


@dataclass(frozen=True, slots=True)
class BasisObservation:
    requested_date: str
    observed_date: str | None
    raw_close: float | None
    split_close: float | None
    share_factor_to_target_basis: float | None


@dataclass(frozen=True, slots=True)
class FloatJoinRow:
    symbol: str
    cik: str
    first_market_qualified_at: str
    method: str
    estimated_float_shares: int | None
    current_outstanding_target_basis: int | None
    float_pillar_pass: bool | None
    public_float_usd: float | None
    public_float_measure_date: str | None
    public_float_accession: str | None
    public_float_price_used: float | None
    public_float_price_date: str | None
    anchor_outstanding_target_basis: int | None
    current_outstanding_accession: str | None
    current_outstanding_measure_date: str | None
    notes: tuple[str, ...]


def _local_dates(frame: pd.DataFrame) -> list[date]:
    return list(frame.index.tz_convert(ET).date)


def _observe_basis(raw: pd.DataFrame, split: pd.DataFrame, requested: date) -> BasisObservation:
    if raw.empty or split.empty:
        return BasisObservation(requested.isoformat(), None, None, None, None)
    raw_dates = _local_dates(raw)
    split_dates = _local_dates(split)
    common = sorted(set(raw_dates) & set(split_dates))
    if not common:
        return BasisObservation(requested.isoformat(), None, None, None, None)
    prior = [d for d in common if d <= requested]
    observed = prior[-1] if prior else common[0]
    raw_row = raw.iloc[raw_dates.index(observed)]
    split_row = split.iloc[split_dates.index(observed)]
    raw_close = float(raw_row["close"])
    split_close = float(split_row["close"])
    factor = None
    if raw_close > 0 and split_close > 0:
        factor = raw_close / split_close
    return BasisObservation(
        requested.isoformat(), observed.isoformat(), raw_close, split_close, factor
    )


def _normalize_shares(shares: int, basis: BasisObservation) -> int | None:
    if basis.share_factor_to_target_basis is None:
        return None
    return max(1, int(round(shares * basis.share_factor_to_target_basis)))


def _estimate_row(candidate: dict, observations: dict[str, BasisObservation]) -> FloatJoinRow:
    symbol = candidate["symbol"]
    notes: list[str] = []
    public = candidate.get("public_float")
    anchor = candidate.get("anchor_outstanding")
    current = candidate.get("current_outstanding")

    current_norm = None
    if current:
        current_basis = observations.get(f"current:{current['measure_date']}")
        if current_basis:
            current_norm = _normalize_shares(int(current["shares"]), current_basis)
        if current_norm is None:
            notes.append("current outstanding share basis could not be normalized from market data")

    if not public:
        if current_norm is not None and current_norm < FLOAT_LIMIT:
            return FloatJoinRow(
                symbol=symbol,
                cik=candidate["cik"],
                first_market_qualified_at=candidate["first_market_qualified_at"],
                method="sec_outstanding_shares_upper_bound",
                estimated_float_shares=current_norm,
                current_outstanding_target_basis=current_norm,
                float_pillar_pass=True,
                public_float_usd=None,
                public_float_measure_date=None,
                public_float_accession=None,
                public_float_price_used=None,
                public_float_price_date=None,
                anchor_outstanding_target_basis=None,
                current_outstanding_accession=current["accession"] if current else None,
                current_outstanding_measure_date=current["measure_date"] if current else None,
                notes=tuple(notes + ["float is at most total common shares outstanding"]),
            )
        notes.append("no eligible SEC EntityPublicFloat disclosure before qualification")
        return FloatJoinRow(
            symbol=symbol,
            cik=candidate["cik"],
            first_market_qualified_at=candidate["first_market_qualified_at"],
            method="unknown_missing_public_float",
            estimated_float_shares=None,
            current_outstanding_target_basis=current_norm,
            float_pillar_pass=None,
            public_float_usd=None,
            public_float_measure_date=None,
            public_float_accession=None,
            public_float_price_used=None,
            public_float_price_date=None,
            anchor_outstanding_target_basis=None,
            current_outstanding_accession=current["accession"] if current else None,
            current_outstanding_measure_date=current["measure_date"] if current else None,
            notes=tuple(notes),
        )

    public_basis = observations.get(f"public:{public['measure_date']}")
    if not public_basis or not public_basis.split_close or public_basis.split_close <= 0:
        notes.append("historical split-adjusted price unavailable for public-float measure date")
        return FloatJoinRow(
            symbol=symbol,
            cik=candidate["cik"],
            first_market_qualified_at=candidate["first_market_qualified_at"],
            method="unknown_missing_public_float_price",
            estimated_float_shares=None,
            current_outstanding_target_basis=current_norm,
            float_pillar_pass=None,
            public_float_usd=float(public["public_float_usd"]),
            public_float_measure_date=public["measure_date"],
            public_float_accession=public["accession"],
            public_float_price_used=None,
            public_float_price_date=None,
            anchor_outstanding_target_basis=None,
            current_outstanding_accession=current["accession"] if current else None,
            current_outstanding_measure_date=current["measure_date"] if current else None,
            notes=tuple(notes),
        )

    anchor_float = max(1, int(round(float(public["public_float_usd"]) / public_basis.split_close)))
    estimated = anchor_float
    anchor_norm = None
    method = "sec_public_float_usd_div_split_adjusted_historical_price"

    if anchor and current:
        anchor_basis = observations.get(f"anchor:{anchor['measure_date']}")
        if anchor_basis:
            anchor_norm = _normalize_shares(int(anchor["shares"]), anchor_basis)
        if anchor_norm is not None and current_norm is not None:
            affiliate = max(anchor_norm - anchor_float, 0)
            estimated = max(anchor_float, current_norm - affiliate)
            method = "sec_public_float_anchor_plus_split_normalized_outstanding_rollforward"
        else:
            notes.append("outstanding-share roll-forward skipped because a share basis was unavailable")

    return FloatJoinRow(
        symbol=symbol,
        cik=candidate["cik"],
        first_market_qualified_at=candidate["first_market_qualified_at"],
        method=method,
        estimated_float_shares=estimated,
        current_outstanding_target_basis=current_norm,
        float_pillar_pass=estimated < FLOAT_LIMIT,
        public_float_usd=float(public["public_float_usd"]),
        public_float_measure_date=public["measure_date"],
        public_float_accession=public["accession"],
        public_float_price_used=public_basis.split_close,
        public_float_price_date=public_basis.observed_date,
        anchor_outstanding_target_basis=anchor_norm,
        current_outstanding_accession=current["accession"] if current else None,
        current_outstanding_measure_date=current["measure_date"] if current else None,
        notes=tuple(notes),
    )


def _download_basis(
    client: AlpacaDataClient,
    symbol: str,
    dates: list[date],
    *,
    trading_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not dates:
        return pd.DataFrame(), pd.DataFrame()
    start_date = min(dates) - timedelta(days=14)
    end_date = max(dates) + timedelta(days=15)
    start = datetime.combine(start_date, time(0), timezone.utc)
    end = datetime.combine(end_date, time(0), timezone.utc)
    raw = client.bars(
        [symbol], timeframe="1Day", start=start, end=end, feed="sip",
        adjustment="raw", asof=trading_date,
    ).get(symbol, pd.DataFrame())
    split = client.bars(
        [symbol], timeframe="1Day", start=start, end=end, feed="sip",
        adjustment="split", asof=trading_date,
    ).get(symbol, pd.DataFrame())
    return raw, split


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="research/reference_days/2026-07-09/sec_float_compact.json")
    parser.add_argument("--output", default="sec-float-join-artifact")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    trading_date = date.fromisoformat(payload["trading_date"])
    client = AlpacaDataClient.from_env()
    rows: list[FloatJoinRow] = []
    basis_audit: dict[str, dict[str, dict]] = {}

    for candidate in payload["candidates"]:
        symbol = candidate["symbol"]
        tagged_dates: list[tuple[str, date]] = []
        for tag, key in (("public", "public_float"), ("anchor", "anchor_outstanding"), ("current", "current_outstanding")):
            disclosure = candidate.get(key)
            if disclosure:
                tagged_dates.append((tag, date.fromisoformat(disclosure["measure_date"])))
        raw, split = _download_basis(client, symbol, [d for _, d in tagged_dates], trading_date=trading_date)
        observations: dict[str, BasisObservation] = {}
        for tag, requested in tagged_dates:
            observation = _observe_basis(raw, split, requested)
            observations[f"{tag}:{requested.isoformat()}"] = observation
        basis_audit[symbol] = {key: asdict(value) for key, value in observations.items()}
        rows.append(_estimate_row(candidate, observations))

    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([asdict(row) | {"notes": "; ".join(row.notes)} for row in rows])
    frame.to_csv(root / "float_estimates.csv", index=False)
    (root / "basis_audit.json").write_text(json.dumps(basis_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "trading_date": trading_date.isoformat(),
        "candidate_count": len(rows),
        "float_pass_count": sum(row.float_pillar_pass is True for row in rows),
        "float_fail_count": sum(row.float_pillar_pass is False for row in rows),
        "float_unknown_count": sum(row.float_pillar_pass is None for row in rows),
        "methods": {row.symbol: row.method for row in rows},
        "notes": [
            "Public float is converted from SEC dollars using Alpaca split-adjusted historical close as of the test date.",
            "Outstanding-share disclosures are normalized to the test-date share basis using raw/split price ratios before roll-forward.",
            "A missing public-float disclosure can only pass via the conservative upper bound that float cannot exceed total common shares outstanding.",
        ],
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(frame.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
