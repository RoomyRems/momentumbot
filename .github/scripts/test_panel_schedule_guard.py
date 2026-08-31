from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("panel_schedule_guard.py")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("panel_schedule_guard", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = guard
SPEC.loader.exec_module(guard)


ACCOUNT_SCHEDULES = {
    "pre-session": [
        "17 7 24-28,31 8 *",
        "47 8 24-28,31 8 *",
        "17 9 24-28,31 8 *",
        "17 7 1-4 9 *",
        "47 8 1-4 9 *",
        "17 9 1-4 9 *",
    ]
}
DAILY_SCHEDULES = {
    "prerequisite": [
        "29 7 24-28,31 8 *",
        "59 8 24-28,31 8 *",
        "29 9 24-28,31 8 *",
        "29 7 1-4 9 *",
        "59 8 1-4 9 *",
        "29 9 1-4 9 *",
    ],
    "produce": [
        "23 14 24-28,31 8 *",
        "53 14 24-28,31 8 *",
        "23 15 24-28,31 8 *",
        "23 14 1-4 9 *",
        "53 14 1-4 9 *",
        "23 15 1-4 9 *",
    ],
}
MANAGEMENT_SCHEDULES = {
    "management": [
        "11 23 24-28,31 8 *",
        "41 23 24-28,31 8 *",
        "11 0 25-29 8 *",
        "11 23 1-4 9 *",
        "41 23 1-4 9 *",
        "11 0 1-5 9 *",
    ]
}


def run_row(
    run_id: int,
    run_number: int,
    expression: str,
    created_at: str,
    *,
    event: str = "schedule",
) -> dict[str, object]:
    return {
        "id": run_id,
        "run_number": run_number,
        "event": event,
        "display_title": f"Panel scheduler / {expression}",
        "created_at": created_at,
        "status": "completed",
        "conclusion": "success",
    }


def pages(*rows: dict[str, object]) -> list[dict[str, object]]:
    return [{"workflow_runs": list(rows)}]


class PanelScheduleGuardTests(unittest.TestCase):
    def test_cross_midnight_delay_binds_nominal_management_date(self) -> None:
        nominal = guard.nominal_occurrence(
            "0 23 24-28,31 8 *",
            datetime.fromisoformat("2026-08-27T04:07:56+00:00"),
        )
        self.assertEqual(nominal.isoformat(), "2026-08-26T23:00:00+00:00")
        self.assertEqual(nominal.astimezone(guard.NEW_YORK).date().isoformat(), "2026-08-26")

    def test_first_pre_session_wakeup_is_permitted(self) -> None:
        current = run_row(10, 100, ACCOUNT_SCHEDULES["pre-session"][0], "2026-08-28T07:22:00Z")
        decision = guard.resolve_guard(
            run_pages=pages(current),
            current_run_id="10",
            event_schedule=ACCOUNT_SCHEDULES["pre-session"][0],
            phase="pre-session",
            phase_schedules=ACCOUNT_SCHEDULES,
            window_start="02:00:00",
            window_end="06:59:59",
            now=datetime.fromisoformat("2026-08-28T07:23:00+00:00"),
        )
        self.assertTrue(decision["should_attempt"])
        self.assertEqual(decision["trading_date"], "2026-08-28")

    def test_later_redundant_wakeup_is_a_blocked_noop(self) -> None:
        prior = run_row(10, 100, ACCOUNT_SCHEDULES["pre-session"][0], "2026-08-28T07:22:00Z")
        current = run_row(11, 101, ACCOUNT_SCHEDULES["pre-session"][1], "2026-08-28T08:50:00Z")
        decision = guard.resolve_guard(
            run_pages=pages(current, prior),
            current_run_id="11",
            event_schedule=ACCOUNT_SCHEDULES["pre-session"][1],
            phase="pre-session",
            phase_schedules=ACCOUNT_SCHEDULES,
            window_start="02:00:00",
            window_end="06:59:59",
            now=datetime.fromisoformat("2026-08-28T08:51:00+00:00"),
        )
        self.assertFalse(decision["should_attempt"])
        self.assertEqual(decision["blocking_run_id"], "10")

    def test_different_daily_phase_does_not_block_production(self) -> None:
        prior = run_row(20, 200, DAILY_SCHEDULES["prerequisite"][0], "2026-08-28T07:35:00Z")
        current = run_row(21, 201, DAILY_SCHEDULES["produce"][0], "2026-08-28T14:25:00Z")
        decision = guard.resolve_guard(
            run_pages=pages(current, prior),
            current_run_id="21",
            event_schedule=DAILY_SCHEDULES["produce"][0],
            phase="produce",
            phase_schedules=DAILY_SCHEDULES,
            window_start="10:01:00",
            window_end="23:59:59",
            now=datetime.fromisoformat("2026-08-28T14:26:00+00:00"),
        )
        self.assertTrue(decision["should_attempt"])

    def test_prior_failed_run_still_owns_the_one_attempt(self) -> None:
        prior = run_row(20, 200, DAILY_SCHEDULES["produce"][0], "2026-08-28T14:25:00Z")
        prior["conclusion"] = "failure"
        current = run_row(21, 201, DAILY_SCHEDULES["produce"][1], "2026-08-28T14:55:00Z")
        decision = guard.resolve_guard(
            run_pages=pages(current, prior),
            current_run_id="21",
            event_schedule=DAILY_SCHEDULES["produce"][1],
            phase="produce",
            phase_schedules=DAILY_SCHEDULES,
            window_start="10:01:00",
            window_end="23:59:59",
            now=datetime.fromisoformat("2026-08-28T14:56:00+00:00"),
        )
        self.assertFalse(decision["should_attempt"])
        self.assertEqual(decision["blocking_run_id"], "20")

    def test_delayed_pre_session_wakeup_makes_no_provider_attempt(self) -> None:
        current = run_row(10, 100, ACCOUNT_SCHEDULES["pre-session"][0], "2026-08-28T11:10:00Z")
        decision = guard.resolve_guard(
            run_pages=pages(current),
            current_run_id="10",
            event_schedule=ACCOUNT_SCHEDULES["pre-session"][0],
            phase="pre-session",
            phase_schedules=ACCOUNT_SCHEDULES,
            window_start="02:00:00",
            window_end="06:59:59",
            now=datetime.fromisoformat("2026-08-28T11:11:00+00:00"),
        )
        self.assertFalse(decision["should_attempt"])
        self.assertIn("outside", decision["reason"])

    def test_shifted_utc_management_wakeup_maps_to_previous_new_york_date(self) -> None:
        expression = MANAGEMENT_SCHEDULES["management"][2]
        current = run_row(30, 300, expression, "2026-08-29T00:15:00Z")
        decision = guard.resolve_guard(
            run_pages=pages(current),
            current_run_id="30",
            event_schedule=expression,
            phase="management",
            phase_schedules=MANAGEMENT_SCHEDULES,
            window_start="19:00:00",
            window_end="23:59:59",
            now=datetime.fromisoformat("2026-08-29T00:16:00+00:00"),
        )
        self.assertTrue(decision["should_attempt"])
        self.assertEqual(decision["trading_date"], "2026-08-28")

    def test_outside_frozen_panel_is_noop(self) -> None:
        schedules = {"pre-session": ["17 7 23 8 *"]}
        current = run_row(10, 100, schedules["pre-session"][0], "2026-08-23T07:18:00Z")
        decision = guard.resolve_guard(
            run_pages=pages(current),
            current_run_id="10",
            event_schedule=schedules["pre-session"][0],
            phase="pre-session",
            phase_schedules=schedules,
            window_start="02:00:00",
            window_end="06:59:59",
            now=datetime.fromisoformat("2026-08-23T07:19:00+00:00"),
        )
        self.assertFalse(decision["should_attempt"])
        self.assertIn("outside the frozen panel", decision["reason"])

    def test_unknown_schedule_fails_closed(self) -> None:
        current = run_row(10, 100, "1 1 1 1 *", "2026-08-28T07:18:00Z")
        with self.assertRaisesRegex(RuntimeError, "not registered"):
            guard.resolve_guard(
                run_pages=pages(current),
                current_run_id="10",
                event_schedule="1 1 1 1 *",
                phase="pre-session",
                phase_schedules=ACCOUNT_SCHEDULES,
                window_start="02:00:00",
                window_end="06:59:59",
                now=datetime.fromisoformat("2026-08-28T07:19:00+00:00"),
            )

    def test_missing_current_run_fails_closed(self) -> None:
        prior = run_row(10, 100, ACCOUNT_SCHEDULES["pre-session"][0], "2026-08-28T07:18:00Z")
        with self.assertRaisesRegex(RuntimeError, "exactly one current run"):
            guard.resolve_guard(
                run_pages=pages(prior),
                current_run_id="11",
                event_schedule=ACCOUNT_SCHEDULES["pre-session"][0],
                phase="pre-session",
                phase_schedules=ACCOUNT_SCHEDULES,
                window_start="02:00:00",
                window_end="06:59:59",
                now=datetime.fromisoformat("2026-08-28T07:19:00+00:00"),
            )

    def test_malformed_history_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "lacks workflow_runs"):
            guard.resolve_guard(
                run_pages=[{}],
                current_run_id="10",
                event_schedule=ACCOUNT_SCHEDULES["pre-session"][0],
                phase="pre-session",
                phase_schedules=ACCOUNT_SCHEDULES,
                window_start="02:00:00",
                window_end="06:59:59",
                now=datetime.fromisoformat("2026-08-28T07:19:00+00:00"),
            )

    def test_later_numbered_run_does_not_block_current_owner(self) -> None:
        current = run_row(10, 100, ACCOUNT_SCHEDULES["pre-session"][0], "2026-08-28T07:22:00Z")
        later = run_row(11, 101, ACCOUNT_SCHEDULES["pre-session"][1], "2026-08-28T08:50:00Z")
        decision = guard.resolve_guard(
            run_pages=pages(later, current),
            current_run_id="10",
            event_schedule=ACCOUNT_SCHEDULES["pre-session"][0],
            phase="pre-session",
            phase_schedules=ACCOUNT_SCHEDULES,
            window_start="02:00:00",
            window_end="06:59:59",
            now=datetime.fromisoformat("2026-08-28T07:23:00+00:00"),
        )
        self.assertTrue(decision["should_attempt"])

    def test_more_than_eighteen_hour_delay_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "too late"):
            guard.nominal_occurrence(
                "17 7 24 8 *",
                datetime.fromisoformat("2026-08-25T02:00:00+00:00"),
            )

    def test_default_branch_workflows_are_closed_and_validation_only(self) -> None:
        for relative in (
            ".github/workflows/account-session-snapshot.yml",
            ".github/workflows/prospective-daily-source.yml",
            ".github/workflows/prospective-management-window.yml",
        ):
            content = (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
            crons = set(re.findall(r'^\s+- cron: "([^"]+)"$', content, flags=re.MULTILINE))
            self.assertEqual(crons, set(), relative)
            self.assertNotRegex(content, r"(?m)^  schedule:$", relative)
            self.assertIn("Provider-free validation only; the prospective panel is closed", content)
            dispatch = content.split("permissions:", 1)[0]
            self.assertRegex(dispatch, r"(?m)^\s+- validate$")
            self.assertNotRegex(
                dispatch,
                r"(?m)^\s+- (capture|capture-prerequisites|produce|project)$",
                relative,
            )

    def test_closed_workflows_retain_historical_guard_for_audit(self) -> None:
        for relative in (
            ".github/workflows/account-session-snapshot.yml",
            ".github/workflows/prospective-daily-source.yml",
            ".github/workflows/prospective-management-window.yml",
        ):
            content = (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("run-name:", content, relative)
            self.assertIn("github.event.schedule", content.splitlines()[1], relative)
            self.assertIn("panel_schedule_guard.py", content, relative)
            self.assertIn("--current-run-id \"${GITHUB_RUN_ID}\"", content, relative)
            self.assertRegex(content, r"(?m)^  actions: (read|write)$", relative)

    def test_historical_schedule_maps_cover_each_panel_date_three_times(self) -> None:
        for schedule_map in (ACCOUNT_SCHEDULES, DAILY_SCHEDULES, MANAGEMENT_SCHEDULES):
            for phase, expressions in schedule_map.items():
                counts = {date: 0 for date in guard.PANEL_DATES}
                for expression in expressions:
                    minute, hour, day, month, _ = expression.split()
                    for month_value in guard.expand_field(month, 1, 12):
                        for day_value in guard.expand_field(day, 1, 31):
                            try:
                                nominal = datetime(
                                    2026,
                                    month_value,
                                    day_value,
                                    int(hour),
                                    int(minute),
                                    tzinfo=UTC,
                                )
                            except ValueError:
                                continue
                            target = nominal.astimezone(guard.NEW_YORK).date().isoformat()
                            if target in counts:
                                counts[target] += 1
                self.assertEqual(set(counts.values()), {3}, phase)


if __name__ == "__main__":
    unittest.main()
