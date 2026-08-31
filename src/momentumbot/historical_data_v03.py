from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

from .models import StrategyProfile, SymbolContext
from .providers.alpaca import AlpacaDataClient
from .providers.sec_edgar import (
    FloatEstimate,
    ParsedCompanyFacts,
    implied_float_shares,
    roll_forward_float,
)
from .rvol import RvolCurve, coarse_rvol_upper_bound, prior_session_dates, same_time_rvol

ET = ZoneInfo("America/New_York")
_ALLOWED_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "NYSEARCA"}
LEGACY_MIXED_GAIN_BASIS = "split_previous_close_raw_target_close"
SPLIT_CONSISTENT_GAIN_BASIS = "split_previous_close_split_target_close"


def normalize_asset_master(
    rows: list[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    """Return the stable membership fields from one downloaded asset census.

    Alpaca's assets endpoint is a current provider census, not a historical
    membership endpoint. Freezing the exact response fields and a fingerprint
    makes that limitation auditable; it does not convert the census into a
    point-in-time universe.
    """
    normalized: list[dict[str, object]] = []
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        raw_attributes = row.get("attributes")
        attributes = (
            sorted(str(value) for value in raw_attributes)
            if isinstance(raw_attributes, list)
            else []
        )
        raw_tradable = row.get("tradable")
        normalized.append(
            {
                "asset_class": str(row.get("class") or row.get("asset_class") or ""),
                "asset_id": str(row.get("id") or row.get("asset_id") or ""),
                "attributes": attributes,
                "exchange": str(row.get("exchange") or "").upper(),
                "name": str(row.get("name") or ""),
                "status": str(row.get("status") or "unknown").lower(),
                "symbol": symbol,
                "tradable": raw_tradable if isinstance(raw_tradable, bool) else None,
            }
        )
    return tuple(
        sorted(
            normalized,
            key=lambda row: (str(row["symbol"]), str(row["asset_id"])),
        )
    )


def asset_master_fingerprint(rows: list[dict[str, object]]) -> str:
    payload = json.dumps(
        normalize_asset_master(rows),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def asset_master_status_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    counts = Counter(str(row["status"]) for row in normalize_asset_master(rows))
    return dict(sorted(counts.items()))


@dataclass(frozen=True, slots=True)
class DiscoveryRow:
    symbol: str
    status: str
    exchange: str
    previous_close: float
    target_high: float
    max_session_gain_pct: float
    max_session_rvol_upper_bound: float | None
    max_session_rvol: float | None
    rvol_history_sessions: int
    average_daily_volume_50: float
    first_market_qualified_at: str | None
    minute_bars: int
    first_market_qualified_bar_started_at: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryAuditRow:
    symbol: str
    disposition: str
    daily_scan_basis_available: bool
    daily_price_gain_prefilter_pass: bool
    average_daily_volume_50_available: bool
    raw_target_minute_bars_present: bool
    split_target_minute_bars_present: bool
    rvol_history_sessions: int
    coarse_rvol_evaluated: bool
    coarse_rvol_observation_available: bool
    coarse_rvol_prefilter_pass: bool
    exact_rvol_evaluated: bool
    exact_rvol_observation_available: bool
    causal_market_qualified: bool
    first_market_qualified_at: str | None
    first_market_qualified_bar_started_at: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    asset_count: int
    listed_asset_count: int
    daily_superset_count: int
    rvol_prefilter_count: int
    market_candidate_count: int
    asset_master_sha256: str
    asset_status_counts: dict[str, int]
    rows: tuple[DiscoveryRow, ...]
    minutes: dict[str, pd.DataFrame]
    contexts: dict[str, SymbolContext]
    rvol_curves: dict[str, pd.Series]
    acquisition_audit: tuple[DiscoveryAuditRow, ...] = ()


def _discovery_disposition(
    state: dict[str, object],
    *,
    required_rvol_sessions: int,
) -> str:
    if not bool(state["daily_scan_basis_available"]):
        return "excluded_missing_daily_scan_basis"
    if not bool(state["daily_price_gain_prefilter_pass"]):
        return "excluded_daily_price_or_gain_acquisition_filter"
    if not bool(state["average_daily_volume_50_available"]):
        return "excluded_missing_50_session_average_volume"
    if not bool(state["raw_target_minute_bars_present"]):
        return "excluded_missing_raw_target_minute_bars"
    if int(state["rvol_history_sessions"]) < required_rvol_sessions:
        return "excluded_insufficient_rvol_history_sessions"
    if not bool(state["split_target_minute_bars_present"]):
        return "excluded_missing_split_target_minute_bars"
    if not bool(state["coarse_rvol_prefilter_pass"]):
        return "excluded_coarse_rvol_acquisition_filter"
    if not bool(state["causal_market_qualified"]):
        return "excluded_exact_causal_market_rules"
    return "causal_market_candidate"


def _local_date(index: pd.DatetimeIndex) -> pd.Index:
    return pd.Index(index.tz_convert(ET).date)


def _bar_for_date(frame: pd.DataFrame, target: date) -> pd.Series | None:
    if frame.empty:
        return None
    mask = _local_date(frame.index) == target
    matches = frame.loc[mask]
    return matches.iloc[-1] if not matches.empty else None


def _previous_bar(frame: pd.DataFrame, target: date) -> pd.Series | None:
    if frame.empty:
        return None
    local_dates = _local_date(frame.index)
    matches = frame.loc[local_dates < target]
    return matches.iloc[-1] if not matches.empty else None


def _daily_scan_basis(
    raw_frame: pd.DataFrame,
    split_frame: pd.DataFrame,
    target: date,
) -> tuple[float, float, float] | None:
    """Return split-consistent prior close plus raw target high/low.

    A reverse split can make a raw previous close incomparable with the target
    session's raw price. Alpaca's split-adjusted series puts the prior close on
    the target/as-of share basis, while the target day's raw high/low preserve
    the actual prices that traders saw. This keeps corporate actions from being
    misclassified as percentage-gap momentum.
    """
    target_bar = _bar_for_date(raw_frame, target)
    prior_bar = _previous_bar(split_frame, target)
    if target_bar is None or prior_bar is None:
        return None
    prior_close = float(prior_bar["close"])
    high = float(target_bar["high"])
    low = float(target_bar["low"])
    if prior_close <= 0:
        return None
    return prior_close, high, low


def _split_consistent_daily_scan_basis(
    raw_frame: pd.DataFrame,
    split_frame: pd.DataFrame,
    target: date,
) -> tuple[float, float, float, float] | None:
    """Return one consistent gain basis plus the raw target price range.

    Split adjustment may include actions after ``target``.  That factor cannot
    affect the result here because both the prior close and target high use the
    same adjusted series.  The independently fetched raw high/low remain the
    sole authority for the strategy's actual price range.
    """

    raw_target = _bar_for_date(raw_frame, target)
    split_target = _bar_for_date(split_frame, target)
    split_prior = _previous_bar(split_frame, target)
    if raw_target is None or split_target is None or split_prior is None:
        return None
    prior_close = float(split_prior["close"])
    gain_high = float(split_target["high"])
    raw_high = float(raw_target["high"])
    raw_low = float(raw_target["low"])
    if prior_close <= 0 or gain_high <= 0:
        return None
    return prior_close, gain_high, raw_high, raw_low


def _average_volume_before(
    frame: pd.DataFrame,
    target: date,
    sessions: int = 50,
) -> float | None:
    if frame.empty:
        return None
    local_dates = _local_date(frame.index)
    values = (
        pd.to_numeric(frame.loc[local_dates < target, "volume"], errors="coerce")
        .dropna()
        .tail(sessions)
    )
    if len(values) < sessions:
        return None
    average = float(values.mean())
    return average if average > 0 else None


def _feature_bounds(target: date, profile: StrategyProfile) -> tuple[datetime, datetime]:
    start = datetime.combine(target, profile.volume_feature_start, ET)
    end = datetime.combine(target, time(10, 1), ET)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _daily_window(
    target: date,
    lookback_days: int,
    *,
    end_at: datetime | None = None,
) -> tuple[datetime, datetime]:
    start = datetime.combine(
        target - timedelta(days=lookback_days),
        time(0, 0),
        timezone.utc,
    )
    end = datetime.combine(target + timedelta(days=1), time(0, 0), timezone.utc)
    if end_at is not None:
        if end_at.tzinfo is None or end_at.utcoffset() is None:
            raise ValueError("daily bar end must be timezone-aware")
        bounded = end_at.astimezone(timezone.utc)
        if not start < bounded <= end:
            raise ValueError("daily bar end is outside the requested window")
        end = bounded
    return start, end


def _history_window(target: date, profile: StrategyProfile) -> tuple[datetime, datetime]:
    # 120 calendar days safely covers 50 trading sessions under ordinary closures.
    days = max(120, int(profile.rvol_lookback_sessions * 2.2))
    start = datetime.combine(target - timedelta(days=days), time(0, 0), timezone.utc)
    _, end = _feature_bounds(target, profile)
    return start, end


def _scan_values(
    frame: pd.DataFrame,
    *,
    previous_close: float,
    rvol_curve: pd.Series,
    profile: StrategyProfile,
    gain_frame: pd.DataFrame | None = None,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    if frame.empty:
        empty = pd.Series(dtype=float)
        return empty, empty, empty, pd.Series(dtype=bool)
    prices = pd.to_numeric(frame["close"], errors="coerce")
    gain_source = frame if gain_frame is None else gain_frame
    if gain_frame is not None and not gain_frame.index.equals(frame.index):
        raise ValueError("raw-price and normalized-gain minute coverage differs")
    gain_prices = pd.to_numeric(gain_source["close"], errors="coerce")
    gain = (gain_prices / previous_close - 1.0) * 100.0
    rvol = rvol_curve.reindex(frame.index)
    # Alpaca timestamps a 1Min aggregate at the beginning of its interval. Its
    # close, cumulative volume, and the resulting same-time RVOL are not known
    # until the interval completes one minute later. Scan-window eligibility is
    # therefore a property of the decision/availability time, not the index.
    decision_times = frame.index + pd.Timedelta(minutes=1)
    local_times = decision_times.tz_convert(ET).time
    in_scan_window = pd.Series(
        [profile.session_start <= value < profile.no_new_entries_after for value in local_times],
        index=frame.index,
    )
    mask = (
        in_scan_window
        & (gain >= profile.min_percent_gain)
        & (rvol >= profile.min_relative_volume)
        & (prices >= profile.min_price)
        & (prices <= profile.max_price)
    )
    return prices, gain, rvol, mask


def discover_market_day(
    alpaca: AlpacaDataClient,
    *,
    trading_date: date,
    profile: StrategyProfile,
    asset_batch_size: int = 250,
    assets: list[dict[str, object]] | None = None,
    daily_bar_end: datetime | None = None,
    gain_basis: str = LEGACY_MIXED_GAIN_BASIS,
) -> DiscoveryResult:
    """Build a causal market-day acquisition set with exact time-of-day RVOL.

    The full-day daily high is used only as a *superset acquisition filter* so we
    avoid downloading intraday history for tens of thousands of securities. It
    never enters the strategy. A conservative 15-minute historical RVOL upper
    bound then narrows the set before exact one-minute, same-time-of-day RVOL is
    downloaded/calculated for the survivors.

    Percentage-gain comparisons use a split-adjusted previous-session close on
    the trading-date share basis. Execution/price-range checks still use raw
    target-session prices. This prevents a split itself from masquerading as a
    momentum gap while retaining genuine post-split price action.
    """
    if gain_basis not in {
        LEGACY_MIXED_GAIN_BASIS,
        SPLIT_CONSISTENT_GAIN_BASIS,
    }:
        raise ValueError("unsupported market-discovery gain basis")
    assets = list(normalize_asset_master(alpaca.assets() if assets is None else assets))
    listed = [
        row
        for row in assets
        if str(row.get("exchange", "")).upper() in _ALLOWED_EXCHANGES
        and str(row.get("symbol", "")).strip()
    ]
    symbols = sorted({str(row["symbol"]).upper() for row in listed})
    asset_meta = {str(row["symbol"]).upper(): row for row in listed}
    audit_state: dict[str, dict[str, object]] = {
        symbol: {
            "daily_scan_basis_available": False,
            "daily_price_gain_prefilter_pass": False,
            "average_daily_volume_50_available": False,
            "raw_target_minute_bars_present": False,
            "split_target_minute_bars_present": False,
            "rvol_history_sessions": 0,
            "coarse_rvol_evaluated": False,
            "coarse_rvol_observation_available": False,
            "coarse_rvol_prefilter_pass": False,
            "exact_rvol_evaluated": False,
            "exact_rvol_observation_available": False,
            "causal_market_qualified": False,
            "first_market_qualified_bar_started_at": None,
            "first_market_qualified_at": None,
        }
        for symbol in symbols
    }

    coarse_start, coarse_end = _daily_window(
        trading_date,
        8,
        end_at=daily_bar_end,
    )
    coarse_raw = alpaca.bars_batched(
        symbols,
        batch_size=asset_batch_size,
        timeframe="1Day",
        start=coarse_start,
        end=coarse_end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )
    coarse_split = alpaca.bars_batched(
        symbols,
        batch_size=asset_batch_size,
        timeframe="1Day",
        start=coarse_start,
        end=coarse_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )
    superset: list[str] = []
    previous_close: dict[str, float] = {}
    target_high: dict[str, float] = {}
    for symbol, raw_frame in coarse_raw.items():
        split_frame = coarse_split.get(symbol, pd.DataFrame())
        normalized = gain_basis == SPLIT_CONSISTENT_GAIN_BASIS
        basis = (
            _split_consistent_daily_scan_basis(
                raw_frame,
                split_frame,
                trading_date,
            )
            if normalized
            else _daily_scan_basis(raw_frame, split_frame, trading_date)
        )
        if basis is None:
            continue
        audit_state[symbol]["daily_scan_basis_available"] = True
        if normalized:
            prior_close, gain_high, raw_high, raw_low = basis
        else:
            prior_close, raw_high, raw_low = basis
            gain_high = raw_high
        gain_at_high = (gain_high / prior_close - 1.0) * 100.0
        price_intersects = (
            raw_high >= profile.min_price and raw_low <= profile.max_price
        )
        if gain_at_high >= profile.min_percent_gain and price_intersects:
            audit_state[symbol]["daily_price_gain_prefilter_pass"] = True
            superset.append(symbol)
            previous_close[symbol] = prior_close
            target_high[symbol] = raw_high

    history_start, history_end = _daily_window(
        trading_date,
        120,
        end_at=daily_bar_end,
    )
    history = alpaca.bars_batched(
        superset,
        batch_size=asset_batch_size,
        timeframe="1Day",
        start=history_start,
        end=history_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )
    feature_start, feature_end = _feature_bounds(trading_date, profile)
    raw_minutes = alpaca.bars_batched(
        superset,
        batch_size=max(20, min(asset_batch_size, 100)),
        timeframe="1Min",
        start=feature_start,
        end=feature_end,
        feed="sip",
        adjustment="raw",
        asof=trading_date,
    )
    split_current = alpaca.bars_batched(
        superset,
        batch_size=max(20, min(asset_batch_size, 100)),
        timeframe="1Min",
        start=feature_start,
        end=feature_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )

    rvol_history_start, rvol_history_end = _history_window(trading_date, profile)
    coarse_rvol_history = alpaca.bars_batched(
        superset,
        batch_size=max(10, min(asset_batch_size, 40)),
        timeframe="15Min",
        start=rvol_history_start,
        end=rvol_history_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )

    contexts: dict[str, SymbolContext] = {}
    session_dates_by_symbol: dict[str, list[date]] = {}
    upper_curves: dict[str, RvolCurve] = {}
    narrowed: list[str] = []
    intermediate: dict[str, dict[str, object]] = {}

    for symbol in superset:
        daily = history.get(symbol, pd.DataFrame())
        average = _average_volume_before(
            daily,
            trading_date,
            sessions=profile.rvol_lookback_sessions,
        )
        frame = raw_minutes.get(symbol, pd.DataFrame())
        current_split = split_current.get(symbol, pd.DataFrame())
        audit_state[symbol]["average_daily_volume_50_available"] = (
            average is not None
        )
        audit_state[symbol]["raw_target_minute_bars_present"] = not frame.empty
        audit_state[symbol]["split_target_minute_bars_present"] = (
            not current_split.empty
        )
        prior_dates = prior_session_dates(
            daily,
            trading_date=trading_date,
            lookback_sessions=profile.rvol_lookback_sessions,
        )
        session_dates_by_symbol[symbol] = prior_dates
        audit_state[symbol]["rvol_history_sessions"] = len(prior_dates)
        if average is None or frame.empty:
            continue
        contexts[symbol] = SymbolContext(
            symbol=symbol,
            previous_close=previous_close[symbol],
            average_daily_volume_50=average,
            float_shares=None,
            float_asof=None,
        )
        decision_times = frame.index + pd.Timedelta(minutes=1)
        scan_times = pd.Series(
            [
                profile.session_start <= value < profile.no_new_entries_after
                for value in decision_times.tz_convert(ET).time
            ],
            index=frame.index,
        )
        gain_frame = (
            current_split
            if gain_basis == SPLIT_CONSISTENT_GAIN_BASIS
            else frame
        )
        if not gain_frame.index.equals(frame.index):
            raise RuntimeError(
                "raw/split target minute coverage disagrees for " + symbol
            )
        gain = (
            pd.to_numeric(gain_frame["close"], errors="coerce")
            / previous_close[symbol]
            - 1.0
        ) * 100.0
        intermediate[symbol] = {
            "average": average,
            "frame": frame,
            "gain_frame": gain_frame,
            "gain": gain,
            "scan_times": scan_times,
        }
        if len(prior_dates) < profile.rvol_lookback_sessions or current_split.empty:
            continue
        coarse_history = coarse_rvol_history.get(symbol, pd.DataFrame())
        audit_state[symbol]["coarse_rvol_evaluated"] = True
        upper = coarse_rvol_upper_bound(
            current_split,
            coarse_history,
            trading_date=trading_date,
            session_dates=prior_dates,
            start_time=profile.volume_feature_start,
            end_time=profile.no_new_entries_after,
        )
        upper_curves[symbol] = upper
        audit_state[symbol]["coarse_rvol_observation_available"] = bool(
            upper.values.notna().any()
        )
        _, _, _, upper_mask = _scan_values(
            frame,
            previous_close=previous_close[symbol],
            rvol_curve=upper.values,
            profile=profile,
            gain_frame=gain_frame,
        )
        if upper_mask.any():
            audit_state[symbol]["coarse_rvol_prefilter_pass"] = True
            narrowed.append(symbol)

    exact_history = alpaca.bars_batched(
        narrowed,
        batch_size=max(5, min(asset_batch_size, 20)),
        timeframe="1Min",
        start=rvol_history_start,
        end=rvol_history_end,
        feed="sip",
        adjustment="split",
        asof=trading_date,
    )
    exact_curves: dict[str, RvolCurve] = {}
    first_qualified_bar_started: dict[str, str] = {}
    first_qualified: dict[str, str] = {}
    for symbol in narrowed:
        full = exact_history.get(symbol, pd.DataFrame())
        prior_dates = session_dates_by_symbol[symbol]
        audit_state[symbol]["exact_rvol_evaluated"] = True
        exact = same_time_rvol(
            full,
            trading_date=trading_date,
            session_dates=prior_dates,
            start_time=profile.volume_feature_start,
            end_time=profile.no_new_entries_after,
        )
        exact_curves[symbol] = exact
        audit_state[symbol]["exact_rvol_observation_available"] = bool(
            exact.values.notna().any()
        )
        frame = raw_minutes[symbol]
        _, _, _, mask = _scan_values(
            frame,
            previous_close=previous_close[symbol],
            rvol_curve=exact.values,
            profile=profile,
            gain_frame=(
                split_current[symbol]
                if gain_basis == SPLIT_CONSISTENT_GAIN_BASIS
                else frame
            ),
        )
        if mask.any():
            bar_started_at = frame.index[mask][0]
            qualified_at = bar_started_at + pd.Timedelta(minutes=1)
            first_qualified_bar_started[symbol] = bar_started_at.isoformat()
            first_qualified[symbol] = qualified_at.isoformat()
            audit_state[symbol]["causal_market_qualified"] = True
            audit_state[symbol]["first_market_qualified_bar_started_at"] = (
                first_qualified_bar_started[symbol]
            )
            audit_state[symbol]["first_market_qualified_at"] = (
                first_qualified[symbol]
            )

    rows: list[DiscoveryRow] = []
    qualified_minutes: dict[str, pd.DataFrame] = {}
    rvol_curves: dict[str, pd.Series] = {}
    for symbol, values in intermediate.items():
        frame = values["frame"]
        gain = values["gain"]
        scan_times = values["scan_times"]
        assert isinstance(frame, pd.DataFrame)
        assert isinstance(gain, pd.Series)
        assert isinstance(scan_times, pd.Series)
        scan_gain = gain.loc[scan_times]
        upper = upper_curves.get(symbol)
        exact = exact_curves.get(symbol)
        upper_max = None
        if upper is not None:
            upper_values = upper.values.reindex(frame.index).loc[scan_times].replace(
                [float("inf"), float("-inf")],
                pd.NA,
            )
            if upper_values.notna().any():
                upper_max = float(upper_values.max())
        exact_max = None
        if exact is not None:
            exact_values = exact.values.reindex(frame.index).loc[scan_times].replace(
                [float("inf"), float("-inf")],
                pd.NA,
            )
            if exact_values.notna().any():
                exact_max = float(exact_values.max())
        meta = asset_meta.get(symbol, {})
        first = first_qualified.get(symbol)
        first_bar_started = first_qualified_bar_started.get(symbol)
        rows.append(
            DiscoveryRow(
                symbol=symbol,
                status=str(meta.get("status", "")),
                exchange=str(meta.get("exchange", "")),
                previous_close=previous_close[symbol],
                target_high=target_high[symbol],
                max_session_gain_pct=(
                    float(scan_gain.max()) if not scan_gain.empty else float("nan")
                ),
                max_session_rvol_upper_bound=upper_max,
                max_session_rvol=exact_max,
                rvol_history_sessions=len(session_dates_by_symbol.get(symbol, [])),
                average_daily_volume_50=float(values["average"]),
                first_market_qualified_at=first,
                minute_bars=len(frame),
                first_market_qualified_bar_started_at=first_bar_started,
            )
        )
        if first:
            qualified_minutes[symbol] = frame
            rvol_curves[symbol] = exact_curves[symbol].values

    rows.sort(
        key=lambda row: (
            row.first_market_qualified_at is not None,
            row.max_session_gain_pct,
        ),
        reverse=True,
    )
    acquisition_audit = tuple(
        DiscoveryAuditRow(
            symbol=symbol,
            disposition=_discovery_disposition(
                audit_state[symbol],
                required_rvol_sessions=profile.rvol_lookback_sessions,
            ),
            **audit_state[symbol],
        )
        for symbol in symbols
    )
    return DiscoveryResult(
        asset_count=len(assets),
        listed_asset_count=len(symbols),
        daily_superset_count=len(superset),
        rvol_prefilter_count=len(narrowed),
        market_candidate_count=len(first_qualified),
        asset_master_sha256=asset_master_fingerprint(assets),
        asset_status_counts=asset_master_status_counts(assets),
        rows=tuple(rows),
        minutes=qualified_minutes,
        contexts=contexts,
        rvol_curves=rvol_curves,
        acquisition_audit=acquisition_audit,
    )


def estimate_float_from_facts(
    facts: ParsedCompanyFacts,
    *,
    as_of: datetime,
    price_lookup: Callable[[date], float],
) -> FloatEstimate | None:
    eligible_public = [item for item in facts.public_float if item.available_at <= as_of]
    if not eligible_public:
        return None
    public = max(eligible_public, key=lambda item: (item.available_at, item.measure_date))
    anchor = implied_float_shares(public, price_lookup(public.measure_date))
    eligible_outstanding = [
        item for item in facts.outstanding_shares if item.available_at <= as_of
    ]
    if not eligible_outstanding:
        return anchor
    anchor_outstanding = min(
        eligible_outstanding,
        key=lambda item: (
            abs((item.measure_date - public.measure_date).days),
            item.available_at,
        ),
    )
    current = max(
        eligible_outstanding,
        key=lambda item: (item.available_at, item.measure_date),
    )
    if current.shares <= anchor_outstanding.shares:
        return anchor
    return roll_forward_float(
        anchor,
        anchor_outstanding=anchor_outstanding,
        current_outstanding=current,
    )


def _validated_discovery_timings(
    result: DiscoveryResult,
) -> dict[str, tuple[str, str]]:
    def parse_pair(
        bar_started_at: str | None,
        qualified_at: str | None,
        *,
        context: str,
    ) -> tuple[str, str] | None:
        if bar_started_at is None and qualified_at is None:
            return None
        if bar_started_at is None or qualified_at is None:
            raise ValueError(f"{context} qualification timing fields must appear together")
        try:
            bar_started = datetime.fromisoformat(bar_started_at)
            decision = datetime.fromisoformat(qualified_at)
        except ValueError as error:
            raise ValueError(f"{context} qualification timestamps are invalid") from error
        if bar_started.tzinfo is None or decision.tzinfo is None:
            raise ValueError(f"{context} qualification timestamps must be timezone-aware")
        if decision - bar_started != timedelta(minutes=1):
            raise ValueError(
                f"{context} decision timestamp must equal bar start plus one minute"
            )
        return bar_started_at, qualified_at

    record_timings: dict[str, tuple[str, str]] = {}
    seen_record_symbols: set[str] = set()
    for row in result.rows:
        if row.symbol in seen_record_symbols:
            raise ValueError("market discovery records repeat a symbol")
        seen_record_symbols.add(row.symbol)
        timing = parse_pair(
            row.first_market_qualified_bar_started_at,
            row.first_market_qualified_at,
            context=f"discovery record {row.symbol}",
        )
        if timing is not None:
            record_timings[row.symbol] = timing
    if len(record_timings) != result.market_candidate_count:
        raise ValueError("market discovery candidate count disagrees with timing")
    if result.acquisition_audit:
        audit_timings: dict[str, tuple[str, str]] = {}
        seen_audit_symbols: set[str] = set()
        for row in result.acquisition_audit:
            if row.symbol in seen_audit_symbols:
                raise ValueError("market discovery audit repeats a symbol")
            seen_audit_symbols.add(row.symbol)
            timing = parse_pair(
                row.first_market_qualified_bar_started_at,
                row.first_market_qualified_at,
                context=f"acquisition audit {row.symbol}",
            )
            if row.causal_market_qualified != (timing is not None):
                raise ValueError(
                    "market discovery audit qualification flag disagrees with timing"
                )
            if timing is not None:
                audit_timings[row.symbol] = timing
        if audit_timings != record_timings:
            raise ValueError("market discovery audit timing disagrees with records")
    return record_timings


def write_discovery(result: DiscoveryResult, root: Path, *, trading_date: date) -> None:
    validated_timings = _validated_discovery_timings(result)
    root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([asdict(row) for row in result.rows]).to_csv(
        root / "discovery.csv",
        index=False,
    )
    manifest = {
        "schema_version": 4,
        "kind": "market_day_discovery",
        "trading_date": trading_date.isoformat(),
        "asset_count": result.asset_count,
        "asset_master_sha256": result.asset_master_sha256,
        "asset_master_status_counts": result.asset_status_counts,
        "asset_master_source": "alpaca_v2_assets_current_census_all_statuses",
        "listed_asset_count": result.listed_asset_count,
        "daily_superset_count": result.daily_superset_count,
        "rvol_prefilter_count": result.rvol_prefilter_count,
        "market_candidate_count": result.market_candidate_count,
        "universe_complete": False,
        "point_in_time_universe_complete": False,
        "full_scanner_walk_forward_eligible": False,
        "acquisition_prefilter_uses_full_day_high": True,
        "prefilter_is_not_available_to_strategy": True,
        "execution_price_bar_adjustment": "raw",
        "percent_gain_previous_close_adjustment": "split",
        "daily_volume_history_adjustment": "split",
        "rvol_bar_adjustment": "split",
        "rvol_method": "same_time_cumulative_1m",
        "rvol_acquisition_prefilter": "completed_15m_denominator_upper_bound",
        "minute_bar_timestamp_semantics": "bar_start",
        "candidate_decision_time_field": "first_market_qualified_at",
        "candidate_bar_start_field": "first_market_qualified_bar_started_at",
        "decision_availability_offset_seconds": 60,
        "scan_window_applies_to": "decision_availability_timestamp",
        "qualification_timing_validated": True,
        "dual_timestamp_candidate_count": len(validated_timings),
        "notes": [
            "This artifact is a discovery/superset dataset, not yet a runnable complete snapshot.",
            "Float and news are intentionally absent from cross-sectional discovery.",
            (
                "Full-day high is used only to decide what data to acquire and is never "
                "a strategy feature."
            ),
            (
                "Percent gain compares raw target prices with a split-adjusted prior close "
                "on the trading-date share basis."
            ),
            (
                "One-minute close and same-time RVOL become available one minute after "
                "the provider bar-start timestamp."
            ),
        ],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_reference_case(
    *,
    root: Path,
    symbol: str,
    trading_date: date,
    bars: pd.DataFrame,
    context: SymbolContext,
    news_rows: list[dict],
    float_estimate: FloatEstimate | None = None,
    rvol_curve: pd.Series | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    bars_dir = root / "bars"
    bars_dir.mkdir(exist_ok=True)
    bars.reset_index().to_csv(bars_dir / f"{symbol}.csv", index=False)
    if rvol_curve is not None:
        rvol_curve.rename("relative_volume").to_csv(
            root / "rvol.csv",
            index_label="timestamp",
        )
    context_row = {
        "symbol": symbol,
        "previous_close": context.previous_close,
        "average_daily_volume_50": context.average_daily_volume_50,
        "float_shares": float_estimate.value_shares if float_estimate else None,
        "float_asof": float_estimate.available_at.isoformat() if float_estimate else None,
        "float_measure_date": (
            float_estimate.measure_date.isoformat() if float_estimate else None
        ),
        "float_method": float_estimate.method if float_estimate else None,
        "float_source_accession": (
            float_estimate.source_accession if float_estimate else None
        ),
    }
    pd.DataFrame([context_row]).to_csv(root / "contexts.csv", index=False)
    normalized_news = []
    for row in news_rows:
        published = row.get("published_at")
        if not published:
            continue
        normalized_news.append(
            {
                "symbol": symbol,
                "published_at": published,
                "headline_id": row.get("uuid") or row.get("url") or row.get("title"),
                "title": row.get("title"),
                "source": row.get("source"),
                "provider": row.get("provider"),
            }
        )
    pd.DataFrame(
        normalized_news,
        columns=[
            "symbol",
            "published_at",
            "headline_id",
            "title",
            "source",
            "provider",
        ],
    ).to_csv(root / "news.csv", index=False)
    manifest = {
        "schema_version": 3,
        "kind": "reference_case",
        "trading_date": trading_date.isoformat(),
        "symbol": symbol,
        "universe_complete": False,
        "runnable_backtest": False,
        "execution_price_bar_adjustment": "raw",
        "percent_gain_previous_close_adjustment": "split",
        "rvol_bar_adjustment": "split",
        "rvol_complete": rvol_curve is not None,
        "float_complete": float_estimate is not None,
        "news_count": len(normalized_news),
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
