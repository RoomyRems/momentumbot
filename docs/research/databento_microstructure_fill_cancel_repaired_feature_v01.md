# Databento EQPT repaired feature replay v0.1

## Purpose

This child preregisters the smallest real-data verification of the published Fill/Cancel identity repair. It repeats the exact EQPT MBO request that previously stopped at `fill_cancel_unmatched`, substitutes only the registered event-local identity repair, and keeps the threshold-free feature engine unchanged.

The frozen parent repair was published as commit `5db47089adc62a5df46fa85e41f3cc3eb26495c2`, tree `c453a91fe6ce6bb17fa90072a5f7c7822d2dc40e`. The repaired-feature contract content SHA-256 is `b6b85967d420fca8262a399fc929c7308e79563db68a46acd17fd39186ad2e28`.

## Frozen hypothesis

The exact EQPT request will normalize under the published repair, yield at least one complete causal feature snapshot, and replay to the identical full snapshot-sequence digest in a second independent feature engine.

The test changes no feature, window, threshold, case, strategy, risk rule, broker behavior, or runtime authority. The prior aggregate classifier selected the repair before this replay was registered. Ross actions, recaps, labels, P&L, and later prices are prohibited inputs.

## Proposed future execution boundary

The current bundle is unarmed. The execution file `research/strategy/databento-microstructure-fill-cancel-repaired-feature-v0.1-execution.json` is absent, and the workflow listens only for a future direct-child push containing that sole file.

A later owner authorization must bind the exact published unarmed parent and permit only:

- one first-attempt EQPT MBO request;
- one metadata cost quote and one billable-size quote before download;
- at most `$0.003` quoted cost;
- at most `3,000,000` quoted billable bytes;
- no retry, batch request, live subscription, or MBP-10 redownload.

The ceilings are slightly above the previously observed quote for the same EQPT request (`$0.002689146996` and `2,406,208` bytes). If either new quote exceeds its ceiling, the runner makes zero time-series requests.

## Sanitization and cleanup

The raw DBN file may exist only in an ephemeral GitHub runner directory after separate authorization. It is deleted before the report is finalized. The persisted artifact contains only non-reconstructable counts, availability totals, exact-replay booleans, the aggregate quote, and cryptographic digests. It excludes raw records, prices, sizes, order IDs, feature values, credentials, labels, outcomes, exception messages, and temporary paths.

## Success and failure meaning

A pass would verify that the registered Fill/Cancel repair resolves the specific EQPT normalization blocker and that the unchanged feature mechanics replay deterministically on that case. A classified failure remains permanent engineering evidence; it does not authorize changing the repair or selecting a different case.

Neither outcome establishes predictive value, a profitable threshold, Ross Cameron-equivalent discretion, consolidated national Level 2, realistic fills, or profitability. AI remains shadow-only, and no paper or live order authority is created.

## Files

- Registration: `research/strategy/databento-microstructure-fill-cancel-repaired-feature-v0.1.json`
- Execution mechanics: `src/momentumbot/research/databento_fill_cancel_repaired_feature_v01.py`
- CLI: `scripts/run_databento_fill_cancel_repaired_feature_v01.py`
- Inert workflow: `.github/workflows/databento-fill-cancel-repaired-feature-v01.yml`
- Deterministic tests: `tests/test_databento_fill_cancel_repaired_feature_v01.py`
