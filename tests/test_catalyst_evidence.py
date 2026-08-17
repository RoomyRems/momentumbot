import copy
import json
import unittest
from pathlib import Path

from momentumbot.research.catalyst_evidence import (
    CONTRACT_ID,
    build_catalyst_evidence_packets,
    load_catalyst_evidence_contract,
    validate_catalyst_evidence_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "strategy" / "catalyst-evidence-packet-shadow-v0.1.json"
AUDIT = ROOT / "research" / "data-audits" / "catalyst-evidence-packet-shadow-v0.1.json"


def _scanner_row(*, decision, count, first=None, latest=None, status="success"):
    return {
        "symbol": "AAA",
        "activation_time": "2026-01-02T12:00:00+00:00",
        "decision_time": decision,
        "news_provider_status": status,
        "provider_news_event_count_as_of": count,
        "has_provider_news_as_of": status == "success" and count > 0,
        "provider_relative_no_news_as_of": status == "success" and count == 0,
        "first_provider_news_published_at_as_of": first,
        "latest_provider_news_published_at_as_of": latest,
    }


def _event(*, headline_id, published_at, provider_symbols=None, title="AAA signs agreement"):
    symbols = provider_symbols or ["AAA"]
    return {
        "symbol": "AAA",
        "headline_id": headline_id,
        "published_at": published_at,
        "availability_basis": "provider_updated_at",
        "provider": "alpaca-benzinga",
        "provider_story_id": headline_id.split(":")[-1],
        "source": "benzinga",
        "title": title,
        "provider_symbols": symbols,
    }


class CatalystEvidenceTests(unittest.TestCase):
    def test_contract_freezes_evidence_envelope_without_semantic_rule(self):
        payload = load_catalyst_evidence_contract(CONTRACT)
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertFalse(payload["semantic_classification_frozen"])
        self.assertFalse(payload["selection_threshold_frozen"])
        self.assertFalse(payload["ai_order_authority"])

    def test_contract_rejects_ai_order_authority(self):
        payload = load_catalyst_evidence_contract(CONTRACT)
        changed = copy.deepcopy(payload)
        changed["ai_order_authority"] = True
        with self.assertRaisesRegex(ValueError, "must be false"):
            validate_catalyst_evidence_contract(changed)

    def test_frozen_audit_is_pinned_causal_and_non_promotional(self):
        payload = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(payload["contract_id"], CONTRACT_ID)
        self.assertEqual(payload["cross_date_summary"]["packet_count"], 35)
        self.assertEqual(
            payload["cross_date_summary"]["future_symbol_headline_count_excluded"],
            1,
        )
        self.assertFalse(payload["semantic_classification_frozen"])
        self.assertFalse(payload["decision"]["promote_catalyst_rule"])
        self.assertFalse(payload["decision"]["enable_ai_strategy_gate"])

    def test_emits_activation_and_event_change_packets_only(self):
        scanner = [
            _scanner_row(decision="2026-01-02T12:00:00+00:00", count=0),
            _scanner_row(
                decision="2026-01-02T12:01:00+00:00",
                count=1,
                first="2026-01-02T12:00:30+00:00",
                latest="2026-01-02T12:00:30+00:00",
            ),
            _scanner_row(
                decision="2026-01-02T12:02:00+00:00",
                count=1,
                first="2026-01-02T12:00:30+00:00",
                latest="2026-01-02T12:00:30+00:00",
            ),
        ]
        news = {
            "full_window_event_tape": [
                _event(
                    headline_id="provider:1",
                    published_at="2026-01-02T12:00:30+00:00",
                ),
                _event(
                    headline_id="provider:future",
                    published_at="2026-01-02T12:03:00+00:00",
                ),
            ]
        }
        packets = build_catalyst_evidence_packets(reversed(scanner), news)

        self.assertEqual(len(packets), 2)
        self.assertEqual(packets[0]["packet_reason"], "candidate_activation")
        self.assertEqual(packets[0]["events"], [])
        self.assertTrue(packets[0]["provider_relative_no_news_as_of"])
        self.assertEqual(packets[1]["packet_reason"], "provider_event_set_changed")
        self.assertEqual(packets[1]["new_headline_ids"], ["provider:1"])
        self.assertEqual(packets[1]["events"][0]["seconds_old_at_decision"], 30.0)
        self.assertTrue(packets[1]["events"][0]["single_symbol_story"])
        self.assertNotIn("provider:future", str(packets))
        self.assertEqual(len(packets[1]["packet_content_sha256"]), 64)

    def test_preserves_multi_symbol_scope_without_interpreting_it(self):
        scanner = [
            _scanner_row(
                decision="2026-01-02T12:00:00+00:00",
                count=1,
                first="2026-01-02T11:59:00+00:00",
                latest="2026-01-02T11:59:00+00:00",
            )
        ]
        news = {
            "full_window_event_tape": [
                _event(
                    headline_id="provider:roundup",
                    published_at="2026-01-02T11:59:00+00:00",
                    provider_symbols=["AAA", "BBB", "CCC"],
                    title="Three stocks moving premarket",
                )
            ]
        }
        event = build_catalyst_evidence_packets(scanner, news)[0]["events"][0]
        self.assertEqual(event["provider_symbol_count"], 3)
        self.assertFalse(event["single_symbol_story"])
        self.assertEqual(event["title"], "Three stocks moving premarket")

    def test_scanner_news_count_mismatch_fails_closed(self):
        scanner = [_scanner_row(decision="2026-01-02T12:00:00+00:00", count=0)]
        news = {
            "full_window_event_tape": [
                _event(
                    headline_id="provider:1",
                    published_at="2026-01-02T11:59:00+00:00",
                )
            ]
        }
        with self.assertRaisesRegex(ValueError, "event-count lineage mismatch"):
            build_catalyst_evidence_packets(scanner, news)

    def test_duplicate_symbol_headline_fails_closed(self):
        event = _event(
            headline_id="provider:1",
            published_at="2026-01-02T11:59:00+00:00",
        )
        scanner = [
            _scanner_row(
                decision="2026-01-02T12:00:00+00:00",
                count=1,
                first="2026-01-02T11:59:00+00:00",
                latest="2026-01-02T11:59:00+00:00",
            )
        ]
        with self.assertRaisesRegex(ValueError, "duplicate symbol/headline_id"):
            build_catalyst_evidence_packets(
                scanner,
                {"full_window_event_tape": [event, dict(event)]},
            )

    def test_packet_hash_and_order_are_input_order_independent(self):
        scanner = [
            _scanner_row(
                decision="2026-01-02T12:00:00+00:00",
                count=2,
                first="2026-01-02T11:58:00+00:00",
                latest="2026-01-02T11:59:00+00:00",
            )
        ]
        events = [
            _event(headline_id="provider:1", published_at="2026-01-02T11:58:00+00:00"),
            _event(headline_id="provider:2", published_at="2026-01-02T11:59:00+00:00"),
        ]
        forward = build_catalyst_evidence_packets(scanner, {"full_window_event_tape": events})
        reversed_order = build_catalyst_evidence_packets(
            scanner, {"full_window_event_tape": list(reversed(events))}
        )
        self.assertEqual(forward, reversed_order)


if __name__ == "__main__":
    unittest.main()
