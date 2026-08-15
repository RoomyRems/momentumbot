from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum


class CandidateQuality(str, Enum):
    A_QUALITY = "a_quality"
    CONDITIONAL = "conditional"
    REJECT = "reject"


class MomentumPhase(str, Enum):
    FRONT_SIDE = "front_side"
    BACK_SIDE = "back_side"
    RECLAIM = "reclaim"
    UNKNOWN = "unknown"


class ExitReason(str, Enum):
    STOP = "stop"
    RED_CANDLE = "red_candle"
    TOPPING_TAIL = "topping_tail"
    TIME_CUTOFF = "time_cutoff"
    SESSION_LOCKOUT = "session_lockout"
    END_OF_DATA = "end_of_data"


@dataclass(frozen=True, slots=True)
class StrategyProfile:
    """Named policy profile, not an optimizer-friendly bag of knobs."""

    name: str
    min_price: float
    max_price: float
    preferred_min_price: float
    preferred_max_price: float
    min_percent_gain: float
    min_relative_volume: float
    max_float_shares: int
    require_fresh_news_for_a_quality: bool = True
    allow_obvious_no_news_exception: bool = True
    require_top_gainer_rank: int | None = None
    volume_feature_start: time = time(4, 0)
    rvol_lookback_sessions: int = 50
    session_start: time = time(7, 0)
    no_new_entries_after: time = time(10, 0)
    flatten_at: time = time(10, 0)
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    ema_span: int = 9
    max_pullback_bars: int = 5
    max_retrace_fraction: float = 0.50
    max_peak_upper_wick_fraction: float = 0.50
    min_reward_r_to_prior_high: float = 2.0
    tick_size: float = 0.01


def current_general_2026() -> StrategyProfile:
    return StrategyProfile(
        name="current-general-2026",
        min_price=2.0,
        max_price=20.0,
        preferred_min_price=5.0,
        preferred_max_price=10.0,
        min_percent_gain=10.0,
        min_relative_volume=5.0,
        max_float_shares=10_000_000,
    )


def current_small_account_2026() -> StrategyProfile:
    """The stricter small-account screen described in the 2026 challenge plan."""
    return StrategyProfile(
        name="current-small-account-2026",
        min_price=1.50,
        max_price=6.0,
        preferred_min_price=1.50,
        preferred_max_price=6.0,
        min_percent_gain=25.0,
        min_relative_volume=5.0,
        max_float_shares=10_000_000,
        require_top_gainer_rank=3,
    )


@dataclass(frozen=True, slots=True)
class SymbolContext:
    symbol: str
    previous_close: float
    average_daily_volume_50: float
    float_shares: int | None
    float_asof: datetime | None = None


@dataclass(frozen=True, slots=True)
class NewsContext:
    has_fresh_news: bool
    latest_headline_at: datetime | None = None
    headline_id: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    symbol: str
    timestamp: datetime
    price: float
    cumulative_volume: int
    relative_volume: float
    percent_gain: float
    float_shares: int | None
    float_rotation: float | None
    has_fresh_news: bool
    top_gainer_rank: int | None
    pillars: dict[str, bool]
    quality: CandidateQuality
    reasons: tuple[str, ...] = ()

    @property
    def pillar_count(self) -> int:
        return sum(self.pillars.values())

    @property
    def ranking_key(self) -> tuple[float, float, float, float, float, float]:
        quality_rank = {
            CandidateQuality.A_QUALITY: 2.0,
            CandidateQuality.CONDITIONAL: 1.0,
            CandidateQuality.REJECT: 0.0,
        }[self.quality]
        gainer_rank = -(self.top_gainer_rank or 1_000_000)
        float_rank = -(self.float_shares or 10**12)
        return (
            quality_rank,
            float(gainer_rank),
            self.percent_gain,
            self.relative_volume,
            float(self.cumulative_volume),
            float(float_rank),
        )


@dataclass(frozen=True, slots=True)
class PullbackFeatures:
    symbol: str
    evaluated_at: datetime
    pullback_bars: int
    pullback_number: int | None
    peak_high: float
    pullback_low: float
    retrace_fraction: float
    impulse_mean_volume: float
    pullback_mean_volume: float
    peak_upper_wick_fraction: float
    ema9_at_low: float
    vwap_at_low: float
    macd_line: float
    macd_signal: float
    momentum_phase: MomentumPhase


@dataclass(frozen=True, slots=True)
class EntryPlan:
    symbol: str
    created_at: datetime
    trigger_price: float
    stop_price: float
    prior_high: float
    risk_per_share: float
    reward_r_to_prior_high: float
    features: PullbackFeatures
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    name: str
    risk_per_trade_fraction: float
    max_daily_loss_fraction: float
    giveback_fraction: float = 0.50
    max_position_fraction_of_equity: float = 1.0
    slippage_bps: float = 5.0


def paper_safe_risk() -> RiskPolicy:
    return RiskPolicy(
        name="paper-safe",
        risk_per_trade_fraction=0.0025,
        max_daily_loss_fraction=0.01,
        giveback_fraction=0.50,
        max_position_fraction_of_equity=0.50,
    )


@dataclass(frozen=True, slots=True)
class Trade:
    symbol: str
    entry_time: datetime
    entry_price: float
    stop_price: float
    quantity: int
    exit_time: datetime
    exit_price: float
    exit_reason: ExitReason
    initial_risk_dollars: float
    campaign_id: str
    entry_number: int
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def pnl_dollars(self) -> float:
        return (self.exit_price - self.entry_price) * self.quantity

    @property
    def realized_r(self) -> float:
        return self.pnl_dollars / self.initial_risk_dollars if self.initial_risk_dollars else 0.0
