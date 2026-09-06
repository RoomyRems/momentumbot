from __future__ import annotations

import pandas as pd

from .indicators import validate_bars
from .models import CandidateQuality, CandidateSnapshot, NewsContext, StrategyProfile, SymbolContext


def evaluate_candidate(
    bars_so_far: pd.DataFrame,
    context: SymbolContext,
    news: NewsContext,
    profile: StrategyProfile,
    *,
    top_gainer_rank: int | None,
) -> CandidateSnapshot:
    """Evaluate only information available through the final completed bar."""
    validate_bars(bars_so_far)
    if bars_so_far.empty:
        raise ValueError("cannot evaluate an empty bar series")
    if context.previous_close <= 0:
        raise ValueError("previous_close must be positive")
    if context.average_daily_volume_50 <= 0:
        raise ValueError("average_daily_volume_50 must be positive")

    last = bars_so_far.iloc[-1]
    price = float(last["close"])
    cumulative_volume = int(bars_so_far["volume"].sum())
    relative_volume = cumulative_volume / context.average_daily_volume_50
    percent_gain = (price / context.previous_close - 1.0) * 100.0
    float_rotation = (
        cumulative_volume / context.float_shares
        if context.float_shares is not None and context.float_shares > 0
        else None
    )

    pillars = {
        "percent_gain": percent_gain >= profile.min_percent_gain,
        "relative_volume": relative_volume >= profile.min_relative_volume,
        "fresh_news": news.has_fresh_news if profile.require_fresh_news_for_a_quality else True,
        "price": profile.min_price <= price <= profile.max_price,
        "float": context.float_shares is not None
        and context.float_shares < profile.max_float_shares,
    }

    reasons: list[str] = []
    missing = [name for name, passed in pillars.items() if not passed]
    rank_ok = profile.require_top_gainer_rank is None or (
        top_gainer_rank is not None and top_gainer_rank <= profile.require_top_gainer_rank
    )

    if not missing and rank_ok:
        quality = CandidateQuality.A_QUALITY
    elif (
        missing == ["fresh_news"]
        and profile.allow_obvious_no_news_exception
        and top_gainer_rank == 1
        and rank_ok
    ):
        quality = CandidateQuality.CONDITIONAL
        reasons.append("no fresh news; allowed only as the current #1 obvious gainer exception")
    else:
        quality = CandidateQuality.REJECT
        reasons.extend(f"failed pillar: {name}" for name in missing)
        if not rank_ok:
            reasons.append("outside required top-gainer rank")

    if profile.preferred_min_price <= price <= profile.preferred_max_price:
        reasons.append("inside preferred price band")
    if cumulative_volume > context.average_daily_volume_50:
        reasons.append("total session volume already exceeds 50-day average daily volume")

    return CandidateSnapshot(
        symbol=context.symbol,
        timestamp=bars_so_far.index[-1].to_pydatetime(),
        price=price,
        cumulative_volume=cumulative_volume,
        relative_volume=relative_volume,
        percent_gain=percent_gain,
        float_shares=context.float_shares,
        float_rotation=float_rotation,
        has_fresh_news=news.has_fresh_news,
        top_gainer_rank=top_gainer_rank,
        pillars=pillars,
        quality=quality,
        reasons=tuple(reasons),
    )


def rank_candidates(candidates: list[CandidateSnapshot]) -> list[CandidateSnapshot]:
    """Rank without an optimizer-fitted weighted score.

    The hierarchy reflects the corpus: quality first, then attention/leader rank,
    gain, RVOL, total volume, and finally lower float as a tie-breaker.
    """
    return sorted(candidates, key=lambda item: item.ranking_key, reverse=True)
