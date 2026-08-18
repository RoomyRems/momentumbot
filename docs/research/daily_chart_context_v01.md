# Daily-chart context shadow v0.1

Status: **frozen deterministic schema and builder; no held-out runtime artifact, chart threshold, score, or trading authority**.

## Research question

Can the project add auditable daily-chart levels and prior trading history to the causal context snapshot without using the current session's completed daily bar, a future corporate action, recap evidence, or a fitted definition of a “failed pop”?

The registered evaluation panel remains `ross-context-heldout-panel-v0.1`, covering the ten fixed sessions from 2026-07-24 through 2026-08-06. This schema was frozen while that panel's recap inventory and uploaded transcript archive remained unopened.

## Isolated change

This layer accepts point-in-time, split-adjusted SIP daily bars requested with the provider `asof` fixed to the decision session. It emits one hash-bound evidence record for a candidate decision. It does not alter candidate acquisition, scanner thresholds, Micro-v0.1, fills, exits, sizing, or risk.

The builder requires:

- a timezone-aware, ordered, unique daily-bar index;
- OHLCV values with valid price geometry and integer nonnegative volume;
- source session dates strictly before the decision session;
- the exact decision-time candidate price;
- a stable Composite FIGI or the frozen unique-CIK fallback; and
- an identity-continuity verification window covering every included bar through the decision session.

A provider failure is not converted into empty or zero-valued evidence. If no valid prior bar or verified identity window exists, no daily-chart evidence item is emitted and the parent context snapshot keeps the domain absent.

## Frozen deterministic features

The packet retains at most the latest 60 completed sessions and their exact normalized source rows. From those rows it calculates:

- the latest completed session's OHLCV;
- 20- and 50-session simple moving averages;
- 5-, 20-, and 50-session high/low levels with their most recent occurrence dates;
- for up to 20 recent sessions, exact open gap, high excursion, close change, high-to-close fade, upper-wick fraction, and volume relative to the preceding 20-session mean; and
- all available moving-average and trailing-high references above the candidate's decision-time price, ordered by exact percentage distance.

These are measurements, not judgments. The contract freezes no resistance-distance cutoff, failed-pop threshold, chart-quality score, candidate priority, or trade action. Insufficient history remains explicit rather than being imputed.

## Why the 200-day average is deferred

The current identity and corporate-action continuity gate is frozen over 120 calendar days. That safely supports the smaller 60-session source request under ordinary session calendars, with explicit partial coverage for recent listings. It does not support a historically honest 200-session moving average across ticker changes and symbol reuse.

The packet therefore fixes `moving_average_200_available` to false with an explicit deferred status. Adding a 200-day average requires a separately versioned identity-continuity extension; it cannot be silently derived from the present-day ticker.

## Context binding and authority

After a daily-chart runtime artifact is frozen and hashed, `daily_chart_supplemental_evidence` binds an exact record to the `daily_chart` domain of `discretion-context-assessment-shadow-v0.1`. The context builder rehashes the payload in its own snapshot envelope.

The daily record structurally fixes chart score, failed-pop classification, candidate priority, selection, recommendation, order, size, and risk outputs to `null`. An AI shadow may later cite this evidence for the registered chart-context axis, may abstain, and still has no order or risk-increase authority.

## Next valid step

Acquire the exact prior-session bar inputs for every causal candidate on the ten registered dates, using `adjustment=split` and `asof=<decision session>`. Build and validate the daily records label-blind, preserve source sidecars, freeze the aggregate artifact hash, and only then bind the records into context snapshots. Theme/regime evidence remains a separate contract.

Do not inventory or open recap sources until deterministic context snapshots and any semantic shadows are frozen.

## Files

- Contract: `research/strategy/daily-chart-context-shadow-v0.1.json`
- Builder and validators: `src/momentumbot/research/daily_chart_context.py`
- Registration audit: `research/data-audits/daily-chart-context-shadow-v0.1.json`
- Tests: `tests/test_daily_chart_context.py` and `tests/test_context_assessment.py`
