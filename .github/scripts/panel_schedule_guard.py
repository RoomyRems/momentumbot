#!/usr/bin/env python3
"""Bind delayed GitHub cron events to one causal panel attempt.

GitHub schedule events can be delayed or dropped. The default-branch panel
workflows therefore register redundant wake-ups, while this provider-free
guard permits only the first emitted run for one phase/date. It reconstructs
the nominal cron occurrence so a delayed event cannot cross midnight and claim
the next trading date.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


NEW_YORK = ZoneInfo("America/New_York")
PANEL_DATES = {
    "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27",
    "2026-08-28", "2026-08-31", "2026-09-01", "2026-09-02",
    "2026-09-03", "2026-09-04",
}
MAX_DELAY = timedelta(hours=18)


def parse_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{field} is missing")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"{field} is invalid") from exc
    if result.tzinfo is None:
        raise RuntimeError(f"{field} lacks a timezone")
    return result.astimezone(UTC)


def expand_field(value: str, low: int, high: int) -> set[int]:
    if value == "*":
        return set(range(low, high + 1))
    result: set[int] = set()
    for token in value.split(","):
        parts = token.split("-")
        if not all(part.isdigit() for part in parts) or len(parts) not in {1, 2}:
            raise RuntimeError("cron field is invalid")
        start = int(parts[0])
        end = int(parts[-1])
        if start > end or start < low or end > high:
            raise RuntimeError("cron field is outside its range")
        result.update(range(start, end + 1))
    if not result:
        raise RuntimeError("cron field is empty")
    return result


def nominal_occurrence(expression: str, observed: datetime) -> datetime:
    fields = expression.split()
    if len(fields) != 5 or fields[4] != "*":
        raise RuntimeError("unsupported panel cron expression")
    minutes = expand_field(fields[0], 0, 59)
    hours = expand_field(fields[1], 0, 23)
    days = expand_field(fields[2], 1, 31)
    months = expand_field(fields[3], 1, 12)
    observed = observed.astimezone(UTC)
    candidates: list[datetime] = []
    for day_offset in (0, 1):
        date_value = (observed - timedelta(days=day_offset)).date()
        if date_value.day not in days or date_value.month not in months:
            continue
        for hour in hours:
            for minute in minutes:
                candidate = datetime.combine(date_value, time(hour, minute), tzinfo=UTC)
                if candidate <= observed and observed - candidate <= MAX_DELAY:
                    candidates.append(candidate)
    if not candidates:
        raise RuntimeError("schedule event is too late for an exact nominal occurrence")
    return max(candidates)


def flatten_runs(payload: object) -> list[Mapping[str, Any]]:
    pages = [payload] if isinstance(payload, Mapping) else payload
    if not isinstance(pages, list):
        raise RuntimeError("workflow-run payload is invalid")
    runs: list[Mapping[str, Any]] = []
    for page in pages:
        if not isinstance(page, Mapping) or not isinstance(page.get("workflow_runs"), list):
            raise RuntimeError("workflow-run page lacks workflow_runs")
        if not all(isinstance(row, Mapping) for row in page["workflow_runs"]):
            raise RuntimeError("workflow-run entry is invalid")
        runs.extend(page["workflow_runs"])
    ids = [str(row.get("id", "")) for row in runs]
    if not ids or any(not value.isdigit() for value in ids) or len(ids) != len(set(ids)):
        raise RuntimeError("workflow-run IDs are empty, invalid, or duplicated")
    return runs


def validate_schedule_map(payload: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(payload, Mapping) or not payload:
        raise RuntimeError("phase schedule map is invalid")
    result: dict[str, tuple[str, ...]] = {}
    all_expressions: list[str] = []
    for phase, expressions in payload.items():
        if not isinstance(phase, str) or not isinstance(expressions, list) or not expressions:
            raise RuntimeError("phase schedule entry is invalid")
        if not all(isinstance(value, str) and value for value in expressions):
            raise RuntimeError("phase schedule expression is invalid")
        result[phase] = tuple(expressions)
        all_expressions.extend(expressions)
    if len(all_expressions) != len(set(all_expressions)):
        raise RuntimeError("one cron expression belongs to multiple phases")
    return result


def title_expression(title: object, expressions: Sequence[str]) -> str | None:
    if not isinstance(title, str):
        return None
    return next((value for value in expressions if title.endswith(f" / {value}")), None)


def resolve_guard(
    *, run_pages: object, current_run_id: str, event_schedule: str,
    phase: str, phase_schedules: object, window_start: str,
    window_end: str, now: datetime,
) -> dict[str, object]:
    runs = flatten_runs(run_pages)
    schedules = validate_schedule_map(phase_schedules)
    if phase not in schedules or event_schedule not in schedules[phase]:
        raise RuntimeError("event schedule is not registered for the requested phase")
    expressions = tuple(value for values in schedules.values() for value in values)
    current_matches = [row for row in runs if str(row.get("id")) == current_run_id]
    if len(current_matches) != 1:
        raise RuntimeError("history does not contain exactly one current run")
    current = current_matches[0]
    if current.get("event") != "schedule":
        raise RuntimeError("guard received a non-schedule run")
    if title_expression(current.get("display_title"), expressions) != event_schedule:
        raise RuntimeError("current run title does not bind its cron expression")
    try:
        current_number = int(current["run_number"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("current run number is invalid") from exc

    observed = parse_timestamp(current.get("created_at"), "current created_at")
    nominal = nominal_occurrence(event_schedule, observed)
    target = nominal.astimezone(NEW_YORK).date().isoformat()
    now_utc = now.astimezone(UTC)
    now_et = now_utc.astimezone(NEW_YORK)
    start = time.fromisoformat(window_start)
    end = time.fromisoformat(window_end)
    if start > end or now_utc < observed:
        raise RuntimeError("guard window or clock is invalid")
    decision: dict[str, object] = {
        "should_attempt": False,
        "trading_date": target,
        "phase": phase,
        "nominal_utc": nominal.isoformat(),
        "observed_utc": observed.isoformat(),
        "delay_seconds": int((observed - nominal).total_seconds()),
        "blocking_run_id": "",
    }
    if target not in PANEL_DATES:
        decision["reason"] = "nominal occurrence is outside the frozen panel"
        return decision
    if now_et.date().isoformat() != target or not (start <= now_et.time().replace(tzinfo=None) <= end):
        decision["reason"] = "wake-up arrived outside the registered causal window"
        return decision

    prior: list[Mapping[str, Any]] = []
    for row in runs:
        if str(row.get("id")) == current_run_id or row.get("event") != "schedule":
            continue
        try:
            run_number = int(row["run_number"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("prior run number is invalid") from exc
        if run_number >= current_number:
            continue
        expression = title_expression(row.get("display_title"), expressions)
        if expression is None:
            continue  # Pre-hardening runs had no cron binding in their title.
        prior_phase = next(name for name, values in schedules.items() if expression in values)
        prior_observed = parse_timestamp(row.get("created_at"), "prior created_at")
        prior_target = nominal_occurrence(expression, prior_observed).astimezone(NEW_YORK).date().isoformat()
        if prior_phase == phase and prior_target == target:
            prior.append(row)
    if prior:
        blocker = min(prior, key=lambda row: int(row["run_number"]))
        decision["reason"] = "an earlier wake-up already owns this phase and date"
        decision["blocking_run_id"] = str(blocker["id"])
        return decision
    decision["should_attempt"] = True
    decision["reason"] = "first emitted wake-up inside the registered causal window"
    return decision


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-pages", type=Path, required=True)
    parser.add_argument("--current-run-id", required=True)
    parser.add_argument("--event-schedule", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--phase-schedules-json", required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    parser.add_argument("--github-summary", type=Path)
    parser.add_argument("--now")
    args = parser.parse_args(argv)
    now = parse_timestamp(args.now, "now") if args.now else datetime.now(UTC)
    decision = resolve_guard(
        run_pages=json.loads(args.run_pages.read_text(encoding="utf-8")),
        current_run_id=args.current_run_id,
        event_schedule=args.event_schedule,
        phase=args.phase,
        phase_schedules=json.loads(args.phase_schedules_json),
        window_start=args.window_start,
        window_end=args.window_end,
        now=now,
    )
    with args.github_output.open("a", encoding="utf-8") as handle:
        for key, value in decision.items():
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
            if "\n" in rendered or "\r" in rendered:
                raise RuntimeError("guard output contains a newline")
            handle.write(f"{key}={rendered}\n")
    disposition = "attempt permitted" if decision["should_attempt"] else "blocked no-op"
    if args.github_summary:
        with args.github_summary.open("a", encoding="utf-8") as handle:
            handle.write("## Prospective panel scheduler guard\n\n")
            handle.write(f"- Disposition: **{disposition}**\n")
            for key in ("trading_date", "phase", "nominal_utc", "observed_utc", "delay_seconds", "reason"):
                handle.write(f"- {key.replace('_', ' ').title()}: `{decision[key]}`\n")
            if decision["blocking_run_id"]:
                handle.write(f"- Earlier owning run: `{decision['blocking_run_id']}`\n")
            if not decision["should_attempt"]:
                handle.write("- Provider calls: none from this wake-up.\n")
    if not decision["should_attempt"]:
        print(f"::warning title=Prospective scheduler blocked::{decision['reason']}; no provider call was made")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"panel schedule guard failed closed: {exc}", file=sys.stderr)
        raise
