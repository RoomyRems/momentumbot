from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable

import pandas as pd

from .indicators import upper_wick_fraction, validate_bars
from .models import CandidateQuality, EntryPlan, ExitReason, NewsContext, RiskPolicy, StrategyProfile, SymbolContext, Trade
from .risk import SessionRiskState, size_entry
from .scanner import evaluate_candidate, rank_candidates
from .setup import evaluate_first_pullback_plan


@dataclass(frozen=True, slots=True)
class NewsEvent:
    symbol: str
    published_at: datetime
    headline_id: str


@dataclass(slots=True)
class OpenPosition:
    symbol: str
    entry_time: pd.Timestamp
    entry_price: float
    stop_price: float
    quantity: int
    initial_risk_dollars: float
    campaign_id: str
    entry_number: int
    exit_next_open: ExitReason | None = None


@dataclass(frozen=True, slots=True)
class BacktestResult:
    trades: tuple[Trade, ...]
    candidate_events: int
    plan_events: int
    setup_rejections: dict[str, int]
    rejected_for_fill_slippage: int
    session_locked: bool
    session_lock_reason: str | None

    @property
    def pnl_dollars(self) -> float:
        return sum(trade.pnl_dollars for trade in self.trades)

    @property
    def total_r(self) -> float:
        return sum(trade.realized_r for trade in self.trades)


class Backtester:
    """Causal one-minute simulator for the deterministic baseline."""

    def __init__(self, profile: StrategyProfile, risk_policy: RiskPolicy) -> None:
        self.profile = profile
        self.risk_policy = risk_policy

    def _slippage(self, price: float) -> float:
        return price * self.risk_policy.slippage_bps / 10_000.0

    @staticmethod
    def _news_at(symbol: str, timestamp: pd.Timestamp, events: Iterable[NewsEvent]) -> NewsContext:
        available = [event for event in events if event.symbol == symbol and pd.Timestamp(event.published_at) <= timestamp]
        if not available:
            return NewsContext(False)
        latest = max(available, key=lambda event: event.published_at)
        return NewsContext(True, latest.published_at, latest.headline_id)

    @staticmethod
    def _rvol_at(symbol: str, timestamp: pd.Timestamp, curves: dict[str, pd.Series] | None) -> float | None:
        if curves is None:
            return None
        curve = curves[symbol]
        if curve.index.tz is None:
            raise ValueError("RVOL curve timestamps must be timezone-aware")
        available = curve.loc[:timestamp].dropna()
        return float(available.iloc[-1]) if not available.empty else float("nan")

    def run_day(
        self,
        bars_by_symbol: dict[str, pd.DataFrame],
        contexts: dict[str, SymbolContext],
        news_events: Iterable[NewsEvent],
        *,
        starting_equity: float = 100_000.0,
        relative_volume_by_symbol: dict[str, pd.Series] | None = None,
        indicator_warmup_by_symbol: dict[str, pd.DataFrame] | None = None,
    ) -> BacktestResult:
        if set(bars_by_symbol) != set(contexts):
            raise ValueError("bars_by_symbol and contexts must contain identical symbols")
        if relative_volume_by_symbol is not None and set(relative_volume_by_symbol) != set(bars_by_symbol):
            raise ValueError("RVOL curves and bars must contain identical symbols")
        if indicator_warmup_by_symbol is not None and not set(indicator_warmup_by_symbol).issubset(bars_by_symbol):
            raise ValueError("indicator warmup symbols must be a subset of the research universe")
        if starting_equity <= 0:
            raise ValueError("starting_equity must be positive")
        for bars in bars_by_symbol.values():
            validate_bars(bars)
            if bars.index.tz is None:
                raise ValueError("bar timestamps must be timezone-aware")
        if indicator_warmup_by_symbol is not None:
            for warmup in indicator_warmup_by_symbol.values():
                validate_bars(warmup)
                if warmup.index.tz is None:
                    raise ValueError("indicator warmup timestamps must be timezone-aware")

        news_events = tuple(news_events)
        timestamps = sorted({ts for bars in bars_by_symbol.values() for ts in bars.index})
        pending: dict[str, EntryPlan] = {}
        positions: dict[str, OpenPosition] = {}
        trades: list[Trade] = []
        pullback_plan_count: defaultdict[str, int] = defaultdict(int)
        entry_count: defaultdict[str, int] = defaultdict(int)
        setup_rejections: Counter[str] = Counter()
        candidate_events = plan_events = rejected_for_fill_slippage = 0
        risk_state = SessionRiskState(starting_equity, self.risk_policy)

        for timestamp in timestamps:
            local_time = timestamp.tz_convert("America/New_York").time()
            if local_time < self.profile.session_start:
                continue

            for symbol in list(positions):
                if timestamp not in bars_by_symbol[symbol].index:
                    continue
                bar, position = bars_by_symbol[symbol].loc[timestamp], positions[symbol]
                forced_reason = position.exit_next_open
                if local_time >= self.profile.flatten_at:
                    forced_reason = ExitReason.TIME_CUTOFF
                if risk_state.locked:
                    forced_reason = ExitReason.SESSION_LOCKOUT
                if forced_reason is not None:
                    raw = float(bar["open"])
                    trade = self._close(position, timestamp, raw - self._slippage(raw), forced_reason)
                    trades.append(trade); risk_state.record_realized(trade.pnl_dollars); del positions[symbol]; continue
                if float(bar["open"]) <= position.stop_price:
                    raw = float(bar["open"])
                    trade = self._close(position, timestamp, raw - self._slippage(raw), ExitReason.STOP)
                    trades.append(trade); risk_state.record_realized(trade.pnl_dollars); del positions[symbol]; continue
                if float(bar["low"]) <= position.stop_price:
                    raw = position.stop_price
                    trade = self._close(position, timestamp, raw - self._slippage(raw), ExitReason.STOP)
                    trades.append(trade); risk_state.record_realized(trade.pnl_dollars); del positions[symbol]

            for symbol, plan in list(pending.items()):
                del pending[symbol]
                if risk_state.locked or local_time >= self.profile.no_new_entries_after:
                    continue
                if symbol in positions or timestamp not in bars_by_symbol[symbol].index:
                    continue
                bar = bars_by_symbol[symbol].loc[timestamp]
                if float(bar["high"]) < plan.trigger_price:
                    continue
                raw_entry = max(float(bar["open"]), plan.trigger_price)
                fill = raw_entry + self._slippage(raw_entry)
                actual_risk_per_share = fill - plan.stop_price
                if actual_risk_per_share <= 0:
                    continue
                actual_reward_r = (plan.prior_high - fill) / actual_risk_per_share
                if actual_reward_r < self.profile.min_reward_r_to_prior_high:
                    rejected_for_fill_slippage += 1; continue
                fill_plan = replace(plan, trigger_price=fill, risk_per_share=actual_risk_per_share, reward_r_to_prior_high=actual_reward_r)
                quantity = size_entry(fill_plan, risk_state)
                if quantity < 1:
                    continue
                entry_count[symbol] += 1
                position = OpenPosition(symbol, timestamp, fill, plan.stop_price, quantity, actual_risk_per_share * quantity, f"{timestamp.date().isoformat()}:{symbol}", entry_count[symbol])
                positions[symbol] = position
                if float(bar["low"]) <= plan.stop_price:
                    raw_exit = plan.stop_price
                    trade = self._close(position, timestamp, raw_exit - self._slippage(raw_exit), ExitReason.STOP)
                    trades.append(trade); risk_state.record_realized(trade.pnl_dollars); del positions[symbol]

            for symbol, position in positions.items():
                if timestamp not in bars_by_symbol[symbol].index:
                    continue
                bar = bars_by_symbol[symbol].loc[timestamp]
                if float(bar["close"]) < float(bar["open"]):
                    position.exit_next_open = ExitReason.RED_CANDLE
                elif upper_wick_fraction(bar) >= self.profile.max_peak_upper_wick_fraction:
                    position.exit_next_open = ExitReason.TOPPING_TAIL

            if risk_state.locked or local_time >= self.profile.no_new_entries_after:
                continue
            raw_ranks: list[tuple[str, float]] = []
            for symbol, bars in bars_by_symbol.items():
                history = bars.loc[:timestamp]
                if history.empty:
                    continue
                close = float(history.iloc[-1]["close"])
                raw_ranks.append((symbol, (close / contexts[symbol].previous_close - 1.0) * 100.0))
            raw_ranks.sort(key=lambda item: item[1], reverse=True)
            rank_by_symbol = {symbol: index + 1 for index, (symbol, _) in enumerate(raw_ranks)}

            candidates = []
            for symbol, bars in bars_by_symbol.items():
                if symbol in positions or timestamp not in bars.index:
                    continue
                history = bars.loc[:timestamp]
                candidate = evaluate_candidate(
                    history, contexts[symbol], self._news_at(symbol, timestamp, news_events), self.profile,
                    top_gainer_rank=rank_by_symbol[symbol],
                    relative_volume_override=self._rvol_at(symbol, timestamp, relative_volume_by_symbol),
                )
                if candidate.quality is not CandidateQuality.REJECT:
                    candidate_events += 1; candidates.append(candidate)

            for candidate in rank_candidates(candidates):
                symbol = candidate.symbol
                history = bars_by_symbol[symbol].loc[:timestamp]
                next_pullback_number = pullback_plan_count[symbol] + 1
                evaluation = evaluate_first_pullback_plan(
                    symbol, history, self.profile, pullback_number=next_pullback_number,
                    indicator_warmup=(indicator_warmup_by_symbol or {}).get(symbol),
                )
                plan = evaluation.plan
                if plan is None:
                    setup_rejections[evaluation.reason] += 1; continue
                if next_pullback_number > 2:
                    setup_rejections["later_than_second_pullback"] += 1; continue
                prior = pending.get(symbol)
                if prior is None or prior.features.peak_high != plan.features.peak_high:
                    pullback_plan_count[symbol] += 1
                pending[symbol] = plan; plan_events += 1

        for symbol, position in list(positions.items()):
            bars = bars_by_symbol[symbol]; timestamp = bars.index[-1]; raw = float(bars.iloc[-1]["close"])
            trade = self._close(position, timestamp, raw - self._slippage(raw), ExitReason.END_OF_DATA)
            trades.append(trade); risk_state.record_realized(trade.pnl_dollars); del positions[symbol]

        return BacktestResult(tuple(trades), candidate_events, plan_events, dict(sorted(setup_rejections.items())), rejected_for_fill_slippage, risk_state.locked, risk_state.lock_reason)

    @staticmethod
    def _close(position: OpenPosition, timestamp: pd.Timestamp, exit_price: float, reason: ExitReason) -> Trade:
        return Trade(symbol=position.symbol, entry_time=position.entry_time.to_pydatetime(), entry_price=position.entry_price, stop_price=position.stop_price, quantity=position.quantity, exit_time=timestamp.to_pydatetime(), exit_price=exit_price, exit_reason=reason, initial_risk_dollars=position.initial_risk_dollars, campaign_id=position.campaign_id, entry_number=position.entry_number)
