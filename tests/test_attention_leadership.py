import copy
import json
import unittest
from pathlib import Path

from momentumbot.research.attention_leadership import (
    CONTRACT_ID,
    derive_attention_leadership_rows,
    load_attention_leadership_contract,
    validate_attention_leadership_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "attention-leadership-shadow-v0.1.json"
AUDIT = ROOT / "research" / "data-audits" / "attention-leadership-shadow-v0.1.json"


def _row(
    *,
    symbol,
    decision,
    activation,
    rank,
    gain,
    volume,
    leader,
    leader_gain,
    rank_hash,
    completed=True,
):
    return {
        "symbol": symbol,
        "activation_time": activation,
        "decision_time": decision,
        "candidate_completed_bar_present": completed,
        "percent_gain": gain,
        "cumulative_volume": volume,
        "top_gainer_rank": rank,
        "rank_leader_symbol": leader,
        "rank_leader_percent_gain": leader_gain,
        "rank_input_ordered_sha256": rank_hash,
        "rank_input_complete_for_members_with_completed_bars": True,
        "identity_resolved_member_count": 100,
        "rank_members_with_computable_gain_count": 80,
    }


def _fixture_rows():
    h0, h1, h2 = "0" * 64, "1" * 64, "2" * 64
    return [
        _row(
            symbol="AAA",
            activation="2026-01-02T12:00:00+00:00",
            decision="2026-01-02T12:00:00+00:00",
            rank=2,
            gain=40.0,
            volume=100,
            leader="ZZZ",
            leader_gain=100.0,
            rank_hash=h0,
        ),
        _row(
            symbol="BBB",
            activation="2026-01-02T12:01:00+00:00",
            decision="2026-01-02T12:01:00+00:00",
            rank=3,
            gain=30.0,
            volume=200,
            leader="AAA",
            leader_gain=110.0,
            rank_hash=h1,
        ),
        _row(
            symbol="AAA",
            activation="2026-01-02T12:00:00+00:00",
            decision="2026-01-02T12:01:00+00:00",
            rank=1,
            gain=110.0,
            volume=160,
            leader="AAA",
            leader_gain=110.0,
            rank_hash=h1,
        ),
        _row(
            symbol="AAA",
            activation="2026-01-02T12:00:00+00:00",
            decision="2026-01-02T12:02:00+00:00",
            rank=1,
            gain=None,
            volume=None,
            leader="AAA",
            leader_gain=110.0,
            rank_hash=h2,
            completed=False,
        ),
        _row(
            symbol="BBB",
            activation="2026-01-02T12:01:00+00:00",
            decision="2026-01-02T12:02:00+00:00",
            rank=2,
            gain=50.0,
            volume=275,
            leader="AAA",
            leader_gain=110.0,
            rank_hash=h2,
        ),
    ]


class AttentionLeadershipTests(unittest.TestCase):
    def test_contract_freezes_features_but_no_trading_rule(self):
        payload = load_attention_leadership_contract(CONTRACT)
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertEqual(payload["runtime_strategy_effect"], "none")
        self.assertFalse(payload["selection_threshold_frozen"])
        self.assertNotIn("attention_score", [row["name"] for row in payload["feature_definitions"]])

    def test_contract_rejects_strategy_gate(self):
        payload = load_attention_leadership_contract(CONTRACT)
        changed = copy.deepcopy(payload)
        changed["feature_definitions"][0]["strategy_gate_enabled"] = True
        with self.assertRaisesRegex(ValueError, "cannot be strategy gates"):
            validate_attention_leadership_contract(changed)

    def test_frozen_validation_audit_is_pinned_and_non_promotional(self):
        payload = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertEqual(
            payload["source_scanner_artifact"]["scanner_policy_fingerprint"],
            "ed21becad10855b4a085b6e05b6feac8f21e4ce511a100b2381522154818f42a",
        )
        self.assertEqual(
            payload["source_scanner_artifact"]["artifact_zip_sha256"],
            "dd05dcd58bd3adc20e18416035b2c6b4c517fb57d5d853d63c2b327d1b2a1d12",
        )
        self.assertEqual(
            sum(row["derived_row_count"] for row in payload["date_results"]),
            2213,
        )
        self.assertFalse(payload["policy_promotion_eligible"])
        self.assertFalse(payload["decision"]["promote_attention_rule"])
        self.assertFalse(payload["decision"]["add_top_n_gate"])

    def test_derives_handoff_persistence_competition_and_change(self):
        rows = derive_attention_leadership_rows(reversed(_fixture_rows()))
        by_key = {(row["decision_time"], row["symbol"]): row for row in rows}

        first = by_key[("2026-01-02T12:00:00+00:00", "AAA")]
        self.assertIsNone(first["market_leader_changed_from_prior_minute"])
        self.assertEqual(first["observed_market_leader_tenure_minutes"], 1)
        self.assertEqual(first["candidate_gap_to_leader_pct_points"], 60.0)
        self.assertIsNone(first["candidate_rank_improvement_from_prior_minute"])

        handoff = by_key[("2026-01-02T12:01:00+00:00", "AAA")]
        self.assertTrue(handoff["market_leader_changed_from_prior_minute"])
        self.assertEqual(handoff["prior_observed_market_leader_symbol"], "ZZZ")
        self.assertTrue(handoff["candidate_is_market_leader"])
        self.assertTrue(handoff["candidate_became_market_leader_this_minute"])
        self.assertEqual(handoff["candidate_consecutive_market_leader_minutes"], 1)
        self.assertEqual(handoff["candidate_rank_improvement_from_prior_minute"], 1)
        self.assertEqual(handoff["candidate_gain_change_pct_points_from_prior_minute"], 70.0)
        self.assertEqual(handoff["candidate_gap_change_pct_points_from_prior_minute"], -60.0)
        self.assertEqual(handoff["candidate_volume_change_from_prior_minute"], 60)
        self.assertEqual(handoff["active_market_candidate_count"], 2)
        self.assertEqual(handoff["active_candidates_with_better_market_rank"], 0)

        competitor = by_key[("2026-01-02T12:01:00+00:00", "BBB")]
        self.assertEqual(competitor["active_candidates_with_better_market_rank"], 1)
        self.assertEqual(competitor["minutes_since_candidate_activation"], 0)

    def test_missing_exact_bar_keeps_causal_rank_but_nulls_bar_deltas(self):
        rows = derive_attention_leadership_rows(_fixture_rows())
        missing = next(
            row
            for row in rows
            if row["decision_time"] == "2026-01-02T12:02:00+00:00" and row["symbol"] == "AAA"
        )
        self.assertFalse(missing["candidate_completed_bar_present"])
        self.assertTrue(missing["candidate_is_market_leader"])
        self.assertEqual(missing["candidate_consecutive_market_leader_minutes"], 2)
        self.assertEqual(missing["observed_market_leader_tenure_minutes"], 2)
        self.assertIsNone(missing["candidate_percent_gain"])
        self.assertIsNone(missing["candidate_gain_change_pct_points_from_prior_minute"])
        self.assertIsNone(missing["candidate_gap_to_leader_pct_points"])
        self.assertIsNone(missing["candidate_volume_change_from_prior_minute"])

    def test_later_candidate_cannot_change_earlier_features(self):
        base = _fixture_rows()[:1]
        later = _row(
            symbol="LATE",
            activation="2026-01-02T12:05:00+00:00",
            decision="2026-01-02T12:05:00+00:00",
            rank=4,
            gain=20.0,
            volume=10,
            leader="ZZZ",
            leader_gain=101.0,
            rank_hash="5" * 64,
        )
        without_future = derive_attention_leadership_rows(base)
        with_future = derive_attention_leadership_rows([later, *base])
        self.assertEqual(with_future[0], without_future[0])

    def test_same_minute_rank_state_disagreement_fails_closed(self):
        rows = _fixture_rows()
        rows[1]["rank_leader_symbol"] = "WRONG"
        with self.assertRaisesRegex(ValueError, "disagree within a decision minute"):
            derive_attention_leadership_rows(rows)

    def test_nonconsecutive_observation_resets_handoff_and_tenure(self):
        rows = [_fixture_rows()[0]]
        rows.append(
            _row(
                symbol="AAA",
                activation="2026-01-02T12:00:00+00:00",
                decision="2026-01-02T12:02:00+00:00",
                rank=2,
                gain=45.0,
                volume=150,
                leader="ZZZ",
                leader_gain=101.0,
                rank_hash="2" * 64,
            )
        )
        derived = derive_attention_leadership_rows(rows)
        self.assertIsNone(derived[1]["market_leader_changed_from_prior_minute"])
        self.assertEqual(derived[1]["observed_market_leader_tenure_minutes"], 1)
        self.assertIsNone(derived[1]["candidate_rank_improvement_from_prior_minute"])

    def test_missing_rank_state_keeps_leadership_features_unknown(self):
        row = _row(
            symbol="AAA",
            activation="2026-01-02T12:00:00+00:00",
            decision="2026-01-02T12:00:00+00:00",
            rank=None,
            gain=10.0,
            volume=100,
            leader=None,
            leader_gain=None,
            rank_hash="0" * 64,
        )
        derived = derive_attention_leadership_rows([row])[0]
        self.assertIsNone(derived["market_leader_symbol"])
        self.assertIsNone(derived["observed_market_leader_tenure_minutes"])
        self.assertIsNone(derived["candidate_is_market_leader"])
        self.assertIsNone(derived["active_candidates_with_better_market_rank"])


if __name__ == "__main__":
    unittest.main()
