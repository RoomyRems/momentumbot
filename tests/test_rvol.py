import unittest
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd

from momentumbot.rvol import coarse_rvol_upper_bound, prior_session_dates, same_time_rvol

ET = ZoneInfo("America/New_York")


def bars(rows):
    frame = pd.DataFrame(rows, columns=["timestamp", "volume"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.set_index("timestamp")


class RvolTests(unittest.TestCase):
    def test_same_time_rvol_compares_cumulative_volume_at_same_minute(self):
        history = bars(
            [
                ("2026-07-06T11:00:00Z", 100),  # 07:00 ET
                ("2026-07-06T11:01:00Z", 100),
                ("2026-07-07T11:00:00Z", 100),
                ("2026-07-07T11:01:00Z", 100),
                ("2026-07-09T11:00:00Z", 500),
                ("2026-07-09T11:01:00Z", 500),
            ]
        )
        curve = same_time_rvol(
            history,
            trading_date=date(2026, 7, 9),
            session_dates=[date(2026, 7, 6), date(2026, 7, 7)],
        )
        self.assertAlmostEqual(curve.values.loc["2026-07-09T11:00:00Z"], 5.0)
        self.assertAlmostEqual(curve.values.loc["2026-07-09T11:01:00Z"], 5.0)
        self.assertEqual(curve.history_sessions, 2)

    def test_coarse_curve_is_an_upper_bound_inside_current_bucket(self):
        current = bars(
            [
                ("2026-07-09T11:00:00Z", 500),
                ("2026-07-09T11:01:00Z", 500),
            ]
        )
        historical_15m = bars(
            [
                ("2026-07-06T10:45:00Z", 100),
                ("2026-07-06T11:00:00Z", 300),
                ("2026-07-07T10:45:00Z", 100),
                ("2026-07-07T11:00:00Z", 300),
            ]
        )
        upper = coarse_rvol_upper_bound(
            current,
            historical_15m,
            trading_date=date(2026, 7, 9),
            session_dates=[date(2026, 7, 6), date(2026, 7, 7)],
        )
        # At 07:01 the 07:00-07:14 historical bucket is deliberately excluded
        # from the denominator, so this prefilter cannot understate exact RVOL.
        self.assertGreater(upper.values.loc["2026-07-09T11:01:00Z"], 5.0)

    def test_prior_session_dates_are_chronological_and_bounded(self):
        index = pd.DatetimeIndex(
            [
                pd.Timestamp("2026-07-01 00:00", tz=ET),
                pd.Timestamp("2026-07-02 00:00", tz=ET),
                pd.Timestamp("2026-07-06 00:00", tz=ET),
                pd.Timestamp("2026-07-07 00:00", tz=ET),
                pd.Timestamp("2026-07-09 00:00", tz=ET),
            ]
        ).tz_convert("UTC")
        daily = pd.DataFrame({"volume": [1, 1, 1, 1, 1]}, index=index)
        self.assertEqual(
            prior_session_dates(daily, trading_date=date(2026, 7, 9), lookback_sessions=2),
            [date(2026, 7, 6), date(2026, 7, 7)],
        )


if __name__ == "__main__":
    unittest.main()
