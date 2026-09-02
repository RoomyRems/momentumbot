"""Canonical exact-RVOL alignment for sealed source recovery v0.10.

The exact same-time RVOL calculator intentionally emits a complete minute
grid.  Provider one-minute bars, however, contain only minutes with an
observation.  The scanner reads RVOL only when an exact raw candidate bar is
present, so the canonical source tape must persist the RVOL value at each raw
bar timestamp and must not persist unrelated grid-only timestamps.

This module performs that index projection without filling, interpolating, or
changing any value.  It is additive; the frozen scanner, RVOL calculator, and
v0.2 source-input serializer remain unchanged.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd


def _validate_datetime_index(index: object, *, label: str) -> pd.DatetimeIndex:
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError(f"{label} requires a DatetimeIndex")
    if index.tz is None or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError(f"{label} timestamps are invalid")
    return index


def align_exact_rvol_to_raw_bar_indexes_v10(
    *,
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_exact_rvol_by_symbol: Mapping[str, pd.Series],
) -> dict[str, pd.Series]:
    """Project each dense exact-RVOL curve onto its raw candidate-bar index.

    Every raw timestamp must already exist in the exact RVOL curve.  Extra RVOL
    timestamps are discarded; missing timestamps fail closed.  No new value is
    synthesized, and NaN or infinity already present at an observed timestamp
    is preserved exactly.
    """

    if set(candidate_raw_minute_bars_by_symbol) != set(
        candidate_exact_rvol_by_symbol
    ):
        raise ValueError("candidate raw-bar and RVOL symbols disagree")

    aligned: dict[str, pd.Series] = {}
    for symbol in sorted(candidate_raw_minute_bars_by_symbol):
        frame = candidate_raw_minute_bars_by_symbol[symbol]
        series = candidate_exact_rvol_by_symbol[symbol]
        if not isinstance(frame, pd.DataFrame):
            raise ValueError(f"raw candidate bars for {symbol} must be a DataFrame")
        if not isinstance(series, pd.Series):
            raise ValueError(f"candidate RVOL for {symbol} must be a Series")
        raw_index = _validate_datetime_index(
            frame.index,
            label=f"raw candidate bars for {symbol}",
        )
        rvol_index = _validate_datetime_index(
            series.index,
            label=f"candidate RVOL for {symbol}",
        )
        if not raw_index.difference(rvol_index).empty:
            raise ValueError(
                f"candidate RVOL lacks a raw-bar timestamp for {symbol}"
            )
        projected = series.reindex(raw_index).copy()
        if not projected.index.equals(raw_index):
            raise ValueError(f"candidate RVOL projection changed timestamps for {symbol}")
        aligned[symbol] = projected
    return aligned


__all__ = ["align_exact_rvol_to_raw_bar_indexes_v10"]
