from __future__ import annotations

import pandas as pd


def frame(rows, start="2026-08-12 11:00:00+00:00"):
    index = pd.date_range(start, periods=len(rows), freq="1min")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=index)


def strong_pullback_bars() -> pd.DataFrame:
    """Warm MACD, make a fresh HOD impulse, then a shallow two-bar pullback."""
    rows = []
    price = 4.00
    for _ in range(35):
        close = price + 0.035
        rows.append((price, close + 0.02, price - 0.015, close, 120_000))
        price = close
    rows += [
        (5.225, 5.45, 5.21, 5.42, 500_000),
        (5.42, 5.75, 5.40, 5.72, 600_000),
        (5.72, 6.05, 5.70, 6.00, 700_000),
        (6.00, 6.30, 5.98, 6.27, 800_000),
        (6.27, 6.50, 6.25, 6.46, 900_000),
        (6.46, 6.18, 6.04, 6.10, 180_000),
        (6.10, 6.13, 6.02, 6.08, 150_000),
    ]
    # Correct malformed first pullback row's high: open may exceed high in the literal above.
    rows[-2] = (6.46, 6.47, 6.04, 6.10, 180_000)
    return frame(rows)
