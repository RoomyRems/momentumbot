# Context held-out deterministic runtime v0.1

Status: **registered workflow; not yet successfully materialized or frozen**.

Registered request content SHA-256: `9459660565c6c76c4af2fd09fd8362789bfda89fe57601d0f016b189112bbff0`.

## First build result and repair

Workflow run `32197398999` failed during causal float enrichment on 2026-08-06. Market discovery had completed for all ten dates and retained all 195 candidates; valid float manifests were written for the first nine dates. The diagnostic artifact is `9348281247`, ZIP SHA-256 `feaa127fc2d126603ffd73193b850c67c6bf18e911a6d805db7c79354ef28952`. It is partial, not frozen, not eligible for label review, and not policy evidence.

The exact blocker was an Alpaca 403 for recent SIP data. The basis downloader asked for its usual 15-calendar-day forward buffer even when an SEC measure date equaled the causal trading date. Those later bars were unnecessary because basis observation only selects sessions on or before the measure date. The repair caps the exclusive query end at the day after the causal trading date and rejects any future measure date. SIP feed, raw/split comparisons, decision-date `asof`, float rules, scanner thresholds, and Micro-v0.1 are unchanged. The permanent failure audit is `research/data-audits/context-heldout-runtime-v0.1-run-32197398999-failure-2026-08-18.json`.

## Purpose

This workflow materializes the deterministic evidence side of `ross-context-heldout-panel-v0.1` before any recap inventory or retrospective labels are opened. It does not run a semantic AI reviewer and cannot affect scanner, Micro-v0.1, orders, size, or risk.

## Registered runtime sequence

1. Rebuild the complete-relative-to-provider point-in-time universe for the ten fixed sessions from 2026-07-24 through 2026-08-06.
2. Rebuild market discovery, point-in-time SEC float, publication-timed news, every causal scanner row, and provider-free scanner replay sidecars.
3. Materialize daily-chart records at candidate activation and at scanner decisions where the causal provider-event set changes.
4. Download the exact frozen prior held-out runtime from workflow run `32071946359`, requiring manifest content SHA-256 `2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48`.
5. Use only its completed scanner sessions for 2026-07-17 and 2026-07-20 through 2026-07-23 as the five-session history preceding the new panel. No old Ross labels or comparisons are downloaded or read.
6. Materialize attention, catalyst, and theme/regime records for activation and provider-event-change decisions.
7. Freeze the complete theme runtime before binding its hash into context snapshots.
8. Compose context snapshots with daily evidence when available and an explicit absent daily domain when prior bars are unavailable.
9. Freeze one aggregate artifact, then verify that transcripts, recaps, Ross actions, retrospective labels, later outcomes, semantic assessments, and strategy authority are absent.

## Failure behavior

Provider failures propagate. A rejected frozen candidate, invalid identity lineage, scanner replay mismatch, future headline, current-session daily bar, inconsistent rank lineage, changed prior-runtime hash, or missing source artifact fails the workflow. Missing prior daily history for a valid recent listing is preserved as an explicit unavailable record and leaves the daily-chart domain absent; it is not converted to zeros.

The upload step runs even after failure so diagnostic partial artifacts are preserved, but a partial artifact is not considered frozen or eligible for recap review.

## Outputs

The requested artifact name is `context-heldout-runtime-v0.1`. It contains:

- the reconstructed market/scanner runtime and source sidecars;
- `daily-chart-context-runtime-v0.1`;
- deterministic attention, catalyst, and theme/regime runtimes;
- the composed context-snapshot runtime; and
- top-level causal manifests binding every child hash.

No AI semantic assessment is included in this first deterministic run. That remains a separate shadow step after the deterministic artifact passes.

## Files

- Workflow: `.github/workflows/context-heldout-runtime.yml`
- Market orchestration: `scripts/build_context_heldout_market_runtime.py`
- Daily materialization: `scripts/build_context_daily_chart_runtime.py`
- Theme and snapshot materialization: `scripts/build_context_snapshot_runtime.py`
- Runtime validators: `src/momentumbot/research/context_runtime.py`
- Registered request: `research/data-audits/context-heldout-runtime-request-v0.1.json`
- Tests: `tests/test_context_runtime.py`
