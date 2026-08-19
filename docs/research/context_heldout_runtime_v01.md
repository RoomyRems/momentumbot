# Context held-out deterministic runtime v0.1

Status: **successfully materialized, independently verified, and frozen; no policy promotion**.

Registered request content SHA-256: `9459660565c6c76c4af2fd09fd8362789bfda89fe57601d0f016b189112bbff0`.

## First build result and repair

Workflow run `32197398999` failed during causal float enrichment on 2026-08-06. Market discovery had completed for all ten dates and retained all 195 candidates; valid float manifests were written for the first nine dates. The diagnostic artifact is `9348281247`, ZIP SHA-256 `feaa127fc2d126603ffd73193b850c67c6bf18e911a6d805db7c79354ef28952`. It is partial, not frozen, not eligible for label review, and not policy evidence.

The exact blocker was an Alpaca 403 for recent SIP data. The basis downloader asked for its usual 15-calendar-day forward buffer even when an SEC measure date equaled the causal trading date. Those later bars were unnecessary because basis observation only selects sessions on or before the measure date. The repair caps the exclusive query end at the day after the causal trading date and rejects any future measure date. SIP feed, raw/split comparisons, decision-date `asof`, float rules, scanner thresholds, and Micro-v0.1 are unchanged. The permanent failure audit is `research/data-audits/context-heldout-runtime-v0.1-run-32197398999-failure-2026-08-18.json`.

Workflow run `32204337846` attempt 1 then passed the contract/regression gate but stopped in `build_massive_historical_census.py` on Massive HTTP 429 while a separate provider-heavy census workflow from the same push overlapped. Its diagnostic artifact is `9348619522`, ZIP SHA-256 `d6f89b2c45e3f1fddccbf32103a382fd9200255563e256fe51028f19690a0b96`. After the competing workflow reached a terminal state, the failed job was rerun exactly once without changing code or policy. The permanent audit is `research/data-audits/context-heldout-runtime-v0.1-run-32204337846-attempt-1-failure-2026-08-19.json`.

Attempt 2 completed all ten provider/scanner dates, retained all 195 candidates, and passed provider-independent scanner replay. It then failed in `freeze_market_runtime_manifest()` because `contract_hash` and `request` were not defined in that function. Its diagnostic artifact is `9351037605`, ZIP SHA-256 `08167f2239368ef5b5d752652d48899af3929acdfc3b3d09865822b68375ed1c`. The repair loads and validates the frozen panel contract and runtime request through one shared helper used by both the session-calendar check and final manifest freeze. A deterministic regression now executes the final manifest-binding path and asserts the exact frozen contract and request hashes. The permanent audit is `research/data-audits/context-heldout-runtime-v0.1-run-32204337846-attempt-2-failure-2026-08-19.json`.

Push-triggered run `32243689589` completed the full ten-date market/scanner stage, retained all 195 candidates, and passed provider-independent scanner replay. It then failed on July 28 while materializing daily-chart records because a valid fail-closed scanner row had `price = null` when its exact completed candidate bar was absent, and the downstream builder called `float(None)`. Its diagnostic artifact is `9365791454`, ZIP SHA-256 `377d79ef0613ae2b92633883caf00dba447f7567ae8c1e1af1203455788ead77`. The repair preserves an explicit unavailable daily-chart row with the exact packet reason and scanner disposition. It never carries forward, looks ahead, or substitutes another price; non-null malformed or non-positive prices still fail closed. The permanent audit is `research/data-audits/context-heldout-runtime-v0.1-run-32243689589-attempt-1-failure-2026-08-19.json`.

All four failed-run artifacts remain diagnostic only: they are not frozen runtime results, are not eligible for label review, and cannot support a policy promotion. No recap or transcript inventory was opened for any repair.

## Successful frozen result

Push-triggered workflow run `32260356870` succeeded at exact head `4a9f3512c1a79ae5d0df86f4a83a3864b2aa2ad2` and exact tree `3659efff5dc9567b4e5da3080bc80cc59ddeb327`. Artifact `9376599434`, `context-heldout-runtime-v0.1`, is 39,331,089 bytes and has independently recomputed ZIP SHA-256 `a29186eb092752cfafc031360cacf348bea5e607cb19ce326ddaff2ddfedac1a`, matching GitHub's digest.

Independent verification recomputed all 115 artifact `content_sha256` claims, every parent-child manifest binding, and the compressed scanner sidecar hashes. Provider-independent replay reproduced all 195 retained market candidates and all 18,954 scanner rows. The exact registered dates are 2026-07-24, 07-27, 07-28, 07-29, 07-30, 07-31, 08-03, 08-04, 08-05, and 08-06. The daily-chart runtime contains 285 records and 29 explicit unavailable rows for exact fail-closed scanner decisions with no completed candidate bar and `price = null`; no price was imputed.

The market, daily, deterministic aggregate, and final manifest content SHA-256 values are respectively `7f4a39a9fa0c5963315cc222deca7e40f30dbf83d46d61384c18d3b5a87b5cac`, `e39cc7e606dd34568061d39eb5b1df4706221c5b728813a1b3715f3236a17c30`, `d24a26bf86d4d9a675cb87bd2bbc196956500f17300ec765bf8d3bae9b9d32a4`, and `3567619bfb6b7b2c177d02cc69f15423bf605663519017a6638b0394e4153702`. The runtime binds the exact frozen request hash `9459660565c6c76c4af2fd09fd8362789bfda89fe57601d0f016b189112bbff0` and prior-runtime hash `2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48`.

All label-blind knowledge flags remain intact. The artifact contains no semantic AI or semantic assessments, has no strategy, order, size, or risk authority, and is not eligible for policy promotion, representative-panel claims, a portfolio backtest, or a full-imitation claim. No recap or transcript file was opened or inventoried during verification. The permanent audit is `research/data-audits/context-heldout-runtime-v0.1-run-32260356870-success-2026-08-19.json`.

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

Provider failures propagate. A rejected frozen candidate, invalid identity lineage, scanner replay mismatch, future headline, current-session daily bar, inconsistent rank lineage, changed prior-runtime hash, or missing source artifact fails the workflow. Missing prior daily history for a valid recent listing is preserved as an explicit unavailable record and leaves the daily-chart domain absent; it is not converted to zeros. A valid fail-closed scanner row with no exact completed candidate bar and therefore no decision price is also preserved as explicit unavailable evidence. No prior, next, nearest, or later price is imputed.

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
