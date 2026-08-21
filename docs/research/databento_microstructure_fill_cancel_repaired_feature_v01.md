# Databento EQPT repaired feature replay v0.1

## Purpose

This child preregisters the smallest real-data verification of the published Fill/Cancel identity repair. It repeats the exact EQPT MBO request that previously stopped at `fill_cancel_unmatched`, substitutes only the registered event-local identity repair, and keeps the threshold-free feature engine unchanged.

The frozen parent repair was published as commit `5db47089adc62a5df46fa85e41f3cc3eb26495c2`, tree `c453a91fe6ce6bb17fa90072a5f7c7822d2dc40e`. The repaired-feature contract content SHA-256 is `b6b85967d420fca8262a399fc929c7308e79563db68a46acd17fd39186ad2e28`.

## Frozen hypothesis

The exact EQPT request will normalize under the published repair, yield at least one complete causal feature snapshot, and replay to the identical full snapshot-sequence digest in a second independent feature engine.

The test changes no feature, window, threshold, case, strategy, risk rule, broker behavior, or runtime authority. The prior aggregate classifier selected the repair before this replay was registered. Ross actions, recaps, labels, P&L, and later prices are prohibited inputs.

## Verified result

GitHub Actions run `32520311940`, attempt 1, made the sole authorized EQPT MBO request and completed successfully. The request requoted at `$0.002689146996` and `2,406,208` billable bytes, below the fixed `$0.003` and `3,000,000` byte ceilings.

The repaired parser normalized 42,968 records into 29,159 per-instrument events, matched all 1,346 Fill markers to canonical Cancel removals, and produced 2,289 sampled causal feature snapshots. A second independent feature engine reproduced the identical full snapshot-sequence digest. No retry, threshold, feature value, raw record, credential, retrospective label, strategy change, broker action, or runtime authority was persisted.

The independently verified audit is `research/data-audits/databento-microstructure-fill-cancel-repaired-feature-v0.1-run-32520311940-success-2026-08-21.json`, content SHA-256 `d87addf40a080d132799cb14daf8f6096b661d97369e7ebd9f8e216609cfffbb`.

## Proposed future execution boundary

The registered execution completed once on the first GitHub Actions attempt. Its parent-bound execution file remains permanent provenance and cannot authorize a rerun because the runner requires `GITHUB_RUN_ATTEMPT=1` and the exact published push parent.

The completed authorization permitted only:

- one first-attempt EQPT MBO request;
- one metadata cost quote and one billable-size quote before download;
- at most `$0.003` quoted cost;
- at most `3,000,000` quoted billable bytes;
- no retry, batch request, live subscription, or MBP-10 redownload.

The ceilings are slightly above the previously observed quote for the same EQPT request (`$0.002689146996` and `2,406,208` bytes). If either new quote exceeds its ceiling, the runner makes zero time-series requests.

## Sanitization and cleanup

The raw DBN file may exist only in an ephemeral GitHub runner directory after separate authorization. It is deleted before the report is finalized. The persisted artifact contains only non-reconstructable counts, availability totals, exact-replay booleans, the aggregate quote, and cryptographic digests. It excludes raw records, prices, sizes, order IDs, feature values, credentials, labels, outcomes, exception messages, and temporary paths.

## Success and failure meaning

The pass verifies that the registered Fill/Cancel repair resolves the specific EQPT normalization blocker and that the unchanged feature mechanics replay deterministically on that case.

Neither outcome establishes predictive value, a profitable threshold, Ross Cameron-equivalent discretion, consolidated national Level 2, realistic fills, or profitability. AI remains shadow-only, and no paper or live order authority is created.

## Files

- Registration: `research/strategy/databento-microstructure-fill-cancel-repaired-feature-v0.1.json`
- Execution mechanics: `src/momentumbot/research/databento_fill_cancel_repaired_feature_v01.py`
- CLI: `scripts/run_databento_fill_cancel_repaired_feature_v01.py`
- Inert workflow: `.github/workflows/databento-fill-cancel-repaired-feature-v01.yml`
- Deterministic tests: `tests/test_databento_fill_cancel_repaired_feature_v01.py`
