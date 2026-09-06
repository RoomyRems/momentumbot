from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import pandas as pd

from .models import NewsContext, SymbolContext


@dataclass(frozen=True, slots=True)
class UniverseMember:
    symbol: str
    as_of: date
    active: bool


class BarSource(Protocol):
    def minute_bars(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame: ...
    def daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame: ...


class PointInTimeReferenceSource(Protocol):
    def universe(self, as_of: date) -> list[UniverseMember]: ...
    def symbol_context(self, symbol: str, as_of: datetime) -> SymbolContext: ...


class NewsSource(Protocol):
    def news_context(self, symbol: str, as_of: datetime) -> NewsContext: ...


@dataclass(frozen=True, slots=True)
class ResearchDataContract:
    """The minimum Layer-1 inputs required for a causal market replay."""

    requires_consolidated_minute_ohlcv: bool = True
    requires_extended_hours: bool = True
    requires_previous_close: bool = True
    requires_50_day_average_volume: bool = True
    requires_point_in_time_float: bool = True
    requires_point_in_time_universe: bool = True
    requires_publication_timed_news: bool = True
    requires_corporate_actions: bool = True
    requires_level2: bool = False
