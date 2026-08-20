from __future__ import annotations

import unittest

from momentumbot.models import (
    CandidateQuality,
    NewsContext,
    SymbolContext,
    current_general_2026,
    current_small_account_2026,
)
from momentumbot.scanner import evaluate_candidate
from tests.helpers import frame


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.context = SymbolContext("TEST", 4.0, 200_000, 5_000_000)
        self.bars = frame([(4.2, 4.6, 4.1, 4.5, 600_000), (4.5, 4.9, 4.4, 4.8, 600_000)])

    def test_all_five_pillars_are_a_quality(self):
        candidate = evaluate_candidate(
            self.bars,
            self.context,
            NewsContext(True),
            current_general_2026(),
            top_gainer_rank=1,
        )
        self.assertEqual(candidate.pillar_count, 5)
        self.assertEqual(candidate.quality, CandidateQuality.A_QUALITY)

    def test_missing_news_is_conditional_only_for_number_one_gainer(self):
        candidate = evaluate_candidate(
            self.bars,
            self.context,
            NewsContext(False),
            current_general_2026(),
            top_gainer_rank=1,
        )
        self.assertEqual(candidate.pillar_count, 4)
        self.assertEqual(candidate.quality, CandidateQuality.CONDITIONAL)

        candidate_rank_two = evaluate_candidate(
            self.bars,
            self.context,
            NewsContext(False),
            current_general_2026(),
            top_gainer_rank=2,
        )
        self.assertEqual(candidate_rank_two.quality, CandidateQuality.REJECT)

    def test_total_volume_is_not_a_canonical_pillar(self):
        low_volume = frame([(4.4, 4.6, 4.3, 4.5, 10)])
        context = SymbolContext("TEST", 4.0, 1.0, 5_000_000)
        candidate = evaluate_candidate(
            low_volume,
            context,
            NewsContext(True),
            current_general_2026(),
            top_gainer_rank=1,
        )
        self.assertEqual(
            set(candidate.pillars),
            {"percent_gain", "relative_volume", "fresh_news", "price", "float"},
        )

    def test_small_account_profile_requires_top_three_and_tighter_price_gain(self):
        profile = current_small_account_2026()
        candidate = evaluate_candidate(
            self.bars,
            self.context,
            NewsContext(True),
            profile,
            top_gainer_rank=4,
        )
        self.assertEqual(candidate.quality, CandidateQuality.REJECT)
        self.assertIn("outside required top-gainer rank", candidate.reasons)

    def test_float_is_strictly_below_ten_million(self):
        context = SymbolContext("TEST", 4.0, 200_000, 10_000_000)
        candidate = evaluate_candidate(
            self.bars,
            context,
            NewsContext(True),
            current_general_2026(),
            top_gainer_rank=1,
        )
        self.assertFalse(candidate.pillars["float"])


if __name__ == "__main__":
    unittest.main()
