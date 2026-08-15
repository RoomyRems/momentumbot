import unittest

import pandas as pd

from momentumbot.micro_setup import detect_running_high_pullbacks


class MicroSetupTests(unittest.TestCase):
    def test_pullbacks_are_counted_only_after_candidate_start(self):
        index = pd.date_range("2026-07-09T11:31:00Z", periods=10, freq="10s")
        bars = pd.DataFrame(
            [
                (5.33, 4.08, 1000),
                (5.31, 4.73, 700),
                (5.04, 4.58, 500),
                (5.27, 4.76, 450),
                (5.41, 5.04, 900),
                (5.28, 5.08, 400),
                (5.41, 5.09, 350),
                (5.28, 4.94, 300),
                (5.24, 4.96, 250),
                (6.04, 5.24, 1500),
            ],
            columns=["high", "low", "volume"],
            index=index,
        )
        observations = detect_running_high_pullbacks(bars, start_at=index[0])
        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[0].ordinal, 1)
        self.assertEqual(observations[0].pullback_bars, 3)
        self.assertEqual(observations[0].resumption_time, index[4].to_pydatetime())
        self.assertEqual(observations[1].ordinal, 2)
        self.assertEqual(observations[1].pullback_bars, 4)
        self.assertEqual(observations[1].trough_low, 4.94)
        self.assertEqual(observations[1].resumption_time, index[9].to_pydatetime())

    def test_unconfirmed_pullback_is_not_reported(self):
        index = pd.date_range("2026-07-09T11:31:00Z", periods=3, freq="10s")
        bars = pd.DataFrame([(5.0,4.8,100),(4.9,4.6,80),(4.8,4.5,60)], columns=["high","low","volume"], index=index)
        self.assertEqual(detect_running_high_pullbacks(bars, start_at=index[0]), ())


if __name__ == "__main__":
    unittest.main()
