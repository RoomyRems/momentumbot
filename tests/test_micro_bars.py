import unittest

import pandas as pd

from momentumbot.micro_bars import aggregate_trade_bars, minute_trade_eligibility


class MicroBarTests(unittest.TestCase):
    def test_condition_rules_apply_strictest_semantics(self):
        self.assertTrue(minute_trade_eligibility("C", ["@"]).updates_price)
        odd = minute_trade_eligibility("C", ["@", "I"])
        self.assertFalse(odd.updates_price)
        self.assertTrue(odd.updates_volume)
        bunched = minute_trade_eligibility("C", ["B"])
        self.assertTrue(bunched.updates_price)
        average = minute_trade_eligibility("A", ["B"])
        self.assertFalse(average.updates_price)
        self.assertTrue(average.updates_volume)

    def test_aggregate_ten_second_bars_excludes_odd_lot_from_prices(self):
        index = pd.to_datetime(
            [
                "2026-07-09T11:32:01Z",
                "2026-07-09T11:32:02Z",
                "2026-07-09T11:32:11Z",
            ],
            utc=True,
        )
        trades = pd.DataFrame(
            [
                {"price":6.00,"size":100,"conditions":("@",),"tape":"C"},
                {"price":9.99,"size":5,"conditions":("@","I"),"tape":"C"},
                {"price":6.20,"size":200,"conditions":("@",),"tape":"C"},
            ],
            index=index,
        )
        bars = aggregate_trade_bars(trades, "10s")
        self.assertEqual(len(bars), 2)
        self.assertEqual(float(bars.iloc[0]["high"]), 6.0)
        self.assertEqual(int(bars.iloc[0]["volume"]), 105)
        self.assertEqual(float(bars.iloc[1]["close"]), 6.2)
        self.assertEqual(bars.iloc[0]["high_time"], index[0])
        self.assertEqual(bars.iloc[0]["low_time"], index[0])

    def test_high_low_timestamps_preserve_intrabar_sequence(self):
        index = pd.to_datetime(
            [
                "2026-04-22T12:00:51Z",
                "2026-04-22T12:00:52Z",
                "2026-04-22T12:00:55Z",
            ],
            utc=True,
        )
        trades = pd.DataFrame(
            [
                {"price":8.40,"size":100,"conditions":("@",),"tape":"C"},
                {"price":8.64,"size":100,"conditions":("@",),"tape":"C"},
                {"price":7.78,"size":100,"conditions":("@",),"tape":"C"},
            ],
            index=index,
        )
        bar = aggregate_trade_bars(trades, "10s").iloc[0]
        self.assertEqual(bar["high_time"], index[1])
        self.assertEqual(bar["low_time"], index[2])
        self.assertLess(bar["high_time"], bar["low_time"])

    def test_unknown_condition_fails_closed_and_is_counted(self):
        index = pd.to_datetime(
            ["2026-07-09T11:32:01Z","2026-07-09T11:32:02Z"], utc=True
        )
        trades = pd.DataFrame(
            [
                {"price":6.00,"size":100,"conditions":("@",),"tape":"C"},
                {"price":7.00,"size":50,"conditions":("?",),"tape":"C"},
            ],
            index=index,
        )
        bars = aggregate_trade_bars(trades)
        self.assertEqual(float(bars.iloc[0]["high"]), 6.0)
        self.assertEqual(int(bars.iloc[0]["unknown_condition_count"]), 1)


if __name__ == "__main__":
    unittest.main()
