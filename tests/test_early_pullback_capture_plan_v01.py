from copy import deepcopy
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import urlencode

from momentumbot.research import early_pullback_capture_plan_v01 as m

ROOT = Path(__file__).resolve().parents[1]
DAY = m.DATES[0]


def receipt(request, cursor=None, *, count=1000):
    return {"request": request, "response_sha256": m.fingerprint({"request": request, "cursor": cursor}),
            "row_count": count, "next_url": None if cursor is None else m.CENSUS_ROUTE + "?" + urlencode({"cursor": cursor})}


def chain(count, *, terminal=False):
    pages = []
    for number in range(count):
        request = m.next_census_request(DAY, pages)
        pages.append(receipt(request, None if terminal and number == count - 1 else f"cursor-{number}"))
    return pages


class CapturePlanTests(unittest.TestCase):
    def test_frozen_parent_and_registration(self):
        result = m.validate_registration(ROOT)
        self.assertEqual(result["parent_registration_sha256"], m.PARENT_SHA)
        self.assertEqual(m.parent.validate_registration(ROOT)["content_sha256"], m.PARENT_SHA)

    def test_official_sources_agree_and_keep_provenance_limits(self):
        observation = m.calendar_observation()
        self.assertEqual(observation["sources"][0]["facts"], observation["sources"][1]["facts"])
        self.assertFalse(observation["raw_http_bodies_retained"])
        self.assertFalse(observation["unscheduled_closures_or_security_halts_verified"])
        self.assertIsNone(observation["raw_http_body_hashes"])

    def test_all_dates_full_scheduled_sessions(self):
        rows = m.scheduled_sessions(m.calendar_observation())
        self.assertEqual([r["date"] for r in rows], list(m.DATES))
        for row in rows:
            self.assertEqual(row["scheduled_minutes"], 390)
            self.assertEqual((datetime.fromisoformat(row["close_utc"]) - datetime.fromisoformat(row["open_utc"])).total_seconds(), 23400)

    def test_dst_changes_utc_not_local_hours(self):
        rows = {r["date"]: r for r in m.scheduled_sessions(m.calendar_observation())}
        self.assertIn("14:30:00+00:00", rows["2026-03-06"]["open_utc"])
        self.assertIn("13:30:00+00:00", rows["2026-03-09"]["open_utc"])
        self.assertIn("09:30:00-04:00", rows["2026-05-19"]["open"])

    def test_rehashed_calendar_changes_rejected(self):
        for key, value in [("regular_close", "13:00"), ("closed_dates", []), ("year", 2025)]:
            observation = deepcopy(m.calendar_observation())
            observation["sources"][0]["facts"][key] = value
            observation.pop("content_sha256")
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.scheduled_sessions(m.seal(observation))

    def test_initial_requests_and_ceiling_not_expected_count(self):
        plan = m.capture_plan(m.calendar_observation())
        self.assertEqual(len(plan["initial_requests"]), 31)
        self.assertEqual([r["trading_date"] for r in plan["initial_requests"][1:]], list(m.DATES))
        self.assertEqual(plan["census_limits"]["maximum_total_http_attempts_if_separately_armed"], 601)
        self.assertEqual(len({r["content_sha256"] for r in plan["initial_requests"]}), 31)
        self.assertEqual(plan["initial_requests"][0]["kind"], "current_type_dictionary")

    def test_no_capture_cost_or_financial_authority(self):
        plan = m.capture_plan(m.calendar_observation())
        for key, value in m.BOUNDARY.items():
            self.assertEqual(plan[key], value)
        for key in ("complete_capture_http_ceiling", "paid_per_request_cost_ceilings_usd", "paid_aggregate_cost_ceiling_usd"):
            self.assertIsNone(plan[key])
        self.assertFalse(plan["consumed_provider_check_may_be_reused"])
        self.assertFalse(plan["realized_full_sessions_verified"])

    def test_graph_is_topological_and_all_unresolved_nodes_remain(self):
        seen = set()
        for node in m.dependency_graph():
            self.assertTrue(set(node["depends_on"]) <= seen)
            self.assertNotIn(node["id"], seen)
            seen.add(node["id"])
            self.assertFalse(node["capture_authorized"])
            self.assertIsNone(node["quoted_cost_usd"])
        self.assertEqual(len(seen), 14)
        self.assertTrue({"identity_actions", "float_news", "exit_plan", "paid_quote", "paired_accounts"} <= seen)

    def test_first_page_exact_filters(self):
        first = m.next_census_request(DAY, [])
        self.assertEqual(first["params"], {"market": "stocks", "locale": "us", "active": "true", "date": DAY,
                                          "order": "asc", "sort": "ticker", "limit": 1000})
        self.assertIsNone(first["predecessor_response_sha256"])

    def test_no_replacement_dates_or_bool_page(self):
        for day in ("2025-05-30", "2026-04-03", "2026-03-07", "2026-03-11", True):
            with self.subTest(day=day), self.assertRaises(ValueError):
                m.next_census_request(day, [])
        for number in (True, 0, 21, 1.0):
            with self.assertRaises(ValueError):
                m.census_request(DAY, page=number)

    def test_cursor_request_binds_parent_response_and_date(self):
        pages = chain(2)
        request = m.next_census_request(DAY, pages)
        self.assertEqual(request["page"], 3)
        self.assertEqual(request["params"], {"cursor": "cursor-1"})
        self.assertEqual(request["predecessor_response_sha256"], pages[-1]["response_sha256"])
        self.assertEqual(request["root_query"]["date"], DAY)

    def test_terminal_last_page_20_is_accepted(self):
        self.assertIsNone(m.next_census_request(DAY, chain(20, terminal=True)))

    def test_page_21_blocked_without_truncating_to_success(self):
        with self.assertRaisesRegex(ValueError, "ceiling"):
            m.next_census_request(DAY, chain(20))

    def test_empty_census_is_not_zero_opportunities(self):
        with self.assertRaisesRegex(ValueError, "empty complete census"):
            m.next_census_request(DAY, [receipt(m.census_request(DAY), count=0)])
        pages = chain(1)
        pages.append(receipt(m.next_census_request(DAY, pages), count=0))
        self.assertIsNone(m.next_census_request(DAY, pages))

    def test_empty_nonterminal_page_does_not_imply_exhaustion(self):
        pages = [receipt(m.census_request(DAY), "cursor-a", count=0)]
        self.assertEqual(m.next_census_request(DAY, pages)["page"], 2)

    def test_cursor_cycle_rejected(self):
        pages = chain(2)
        pages[-1]["next_url"] = pages[0]["next_url"]
        with self.assertRaisesRegex(ValueError, "repeated cursor"):
            m.next_census_request(DAY, pages)

    def test_injection_and_route_substitution_rejected(self):
        urls = ["http://api.massive.com/v3/reference/tickers?cursor=a",
            "https://api.polygon.io/v3/reference/tickers?cursor=a",
            "https://api.massive.com:443/v3/reference/tickers?cursor=a",
            "https://user@api.massive.com/v3/reference/tickers?cursor=a",
            "https://api.massive.com/v3/reference/tickers/types?cursor=a",
            m.CENSUS_ROUTE + "?cursor=a#fragment", m.CENSUS_ROUTE + "?cursor=a&apiKey=TEST_SECRET",
            m.CENSUS_ROUTE + "?cursor=a&cursor=b", m.CENSUS_ROUTE + "?cursor=a&date=2026-05-19",
            m.CENSUS_ROUTE + "?cursor=a&active=false", m.CENSUS_ROUTE + "?cursor=a&limit=1",
            m.CENSUS_ROUTE + "?cursor=%0A", m.CENSUS_ROUTE + "?cursor=", m.CENSUS_ROUTE + "?cursor=a\n",
            m.CENSUS_ROUTE + "?cursor=" + "a" * 4100]
        for url in urls:
            page = receipt(m.census_request(DAY), "a")
            page["next_url"] = url
            with self.subTest(url=url[:120]), self.assertRaises(ValueError):
                m.next_census_request(DAY, [page])

    def test_optional_root_parameters_must_match(self):
        page = receipt(m.census_request(DAY), "a")
        page["next_url"] += "&date=" + DAY + "&active=true&limit=1000"
        self.assertEqual(m.next_census_request(DAY, [page])["params"], {"cursor": "a"})

    def test_page_chain_tampering_rejected(self):
        for mutation in ("order", "day", "seal", "predecessor"):
            pages = chain(2)
            if mutation == "order":
                pages.reverse()
            elif mutation == "day":
                pages[-1]["request"] = m.census_request(m.DATES[-1])
            elif mutation == "seal":
                pages[-1]["request"]["content_sha256"] = "0" * 64
            else:
                request = dict(pages[-1]["request"], predecessor_response_sha256="0" * 64)
                request.pop("content_sha256")
                pages[-1]["request"] = m.seal(request)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                m.next_census_request(DAY, pages)

    def test_bad_receipts_and_after_terminal_rejected(self):
        for count in (-1, 1001, True, 0.5):
            with self.assertRaises(ValueError):
                m.next_census_request(DAY, [receipt(m.census_request(DAY), count=count)])
        for extra in ("outcome", "failed_attempt", "symbol"):
            page = receipt(m.census_request(DAY))
            page[extra] = "not-allowed"
            with self.assertRaises(ValueError):
                m.next_census_request(DAY, [page])
        pages = chain(2)
        pages[0]["next_url"] = None
        with self.assertRaises(ValueError):
            m.next_census_request(DAY, pages)

    def test_planning_is_pure_and_deterministic(self):
        pages = chain(3)
        before = deepcopy(pages)
        self.assertEqual(m.next_census_request(DAY, pages), m.next_census_request(DAY, pages))
        self.assertEqual(pages, before)
        self.assertEqual(m.capture_plan(m.calendar_observation()), m.capture_plan(m.calendar_observation()))

    def test_real_cli_normal_optimized_and_no_overwrite(self):
        script = str(ROOT / "scripts/build_early_pullback_capture_plan_v01.py")
        for flags in ([], ["-O"]):
            run = subprocess.run([sys.executable, *flags, script], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('"provider_calls_authorized_now": 0', run.stdout)
        before = (ROOT / m.CONTRACT_PATH).read_bytes()
        run = subprocess.run([sys.executable, script, "--freeze"], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual((ROOT / m.CONTRACT_PATH).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
