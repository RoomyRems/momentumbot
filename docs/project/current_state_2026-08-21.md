# Current project state — 2026-08-21

This checkpoint extends `docs/project/current_state_2026-08-20.md`. The August 19 and August 20 checkpoints remain immutable provenance. If a statement conflicts, this child controls only for work completed and independently verified after the August 20 checkpoint.

## Plain-English position

The project has verified that the repaired Nasdaq order-event parser can turn one real Databento INTJ MBO case into deterministic, threshold-free microstructure feature snapshots. It has **not** yet generalized to the remaining cases: the first EQPT attempt stopped safely because at least one Databento Fill marker did not match a Cancel under the frozen five-field identity. AMC and GMM were therefore not downloaded.

This is an engineering failure, not evidence that the trading idea is profitable or unprofitable. It does identify the next narrow question: which Fill/Cancel identity field or event structure caused the mismatch? A new unarmed, aggregate-only classifier is now implemented to answer that question on a future separately authorized EQPT attempt.

No feature threshold, runtime trading authority, consolidated national Level 2 claim, Ross Cameron imitation claim, or realistic broker-fill claim exists.

The two Alpaca paper accounts remain separately validated. The registered pre-session snapshot scheduler is scheduled for the ten registered market dates from August 24 through September 4 at 09:15 UTC (05:15 ET). The accounts should remain flat and their balances should not be reset during the study.

## Verified real-data results

### INTJ success

- Databento feature-repair workflow `32483408413`, attempt 1, completed successfully at execution head `d1c95d2208175864a56327cc78f0b0082eec6741`.
- The sole INTJ MBO request requoted at `$0.000130802393` and `117,040` billable bytes. Actual billing remains unknown.
- The sanitized result recorded 2,090 records, 1,700 per-instrument events, 61 within-event sequence transitions, and 238 sampled feature snapshots.
- The independent feature replay matched exactly. Signed-tape mechanics were available for all 238 samples at each registered one-, five-, and ten-second window; 1,428 fixed depth-walk scenarios were evaluated.
- The permanent success audit is `research/data-audits/databento-microstructure-feature-diagnostic-v0.3-run-32483408413-success-2026-08-21.json`, content SHA-256 `093f65e4d62b125e370d972a5bd9ee3880b5439d72072dd3fd533e4774d18ebb`.

### Remaining-case safe failure

- Databento feature-coverage workflow `32501827997`, attempt 1, completed with a green workflow conclusion because it classified and sanitized the failure correctly; that green status does not mean all cases succeeded.
- Preflight quoted all three registered requests at `$0.072004777193` and `64,428,784` total billable bytes, below the authorized `$0.08` and `80 MB` ceilings.
- Exactly one timeseries request was made. EQPT downloaded, then normalization stopped with `fill_cancel_unmatched`. No retry occurred, and AMC and GMM were not downloaded.
- Actual billing remains unknown. Raw market data, raw values, feature snapshots, credentials, thresholds, strategy changes, broker actions, and runtime authority were not persisted.
- The permanent safe-failure audit is `research/data-audits/databento-microstructure-feature-coverage-v0.1-run-32501827997-safe-failure-2026-08-21.json`, content SHA-256 `10b8d05287947a3d334b7a0dda26f89549501287bb58fd7d4a06f6db3ebb5bad`.

## New unarmed development

`databento-microstructure-fill-cancel-classifier-v0.1`, content SHA-256 `88a7373d70bacbad2418d900abc0fcce45e3f927d54a88275091bed05c9e44c0`, freezes a single EQPT diagnostic before another provider request. Its pure classifier compares Fill and Cancel multisets under six registered identity projections:

1. exact sequence, order ID, side, price, and size;
2. without sequence;
3. without size;
4. without sequence and size;
5. order ID and side only; and
6. order ID only.

It returns counts only: event counts, Fill/Cancel counts, and per-projection overlap/full-match counts. It never returns or persists raw records, identifiers, prices, sizes, or feature values. It imports no Databento client and makes no provider request.

The execution authorization file is absent. This bundle cannot call Databento or spend credit. A future one-request EQPT diagnostic would require a separate explicit authorization bound to the published parent and would be capped at `$0.003` and `3,000,000` quoted bytes, with one first attempt and no retry.

## Active gates, in order

1. Publish the tested unarmed Fill/Cancel classifier bundle without an execution authorization file.
2. Only after that parent is published, decide whether to authorize its separate one-request EQPT diagnostic under the fixed `$0.003` and `3 MB` ceilings.
3. Use the aggregate result to register exactly one parser repair; do not inspect or publish raw record values and do not select a trading threshold.
4. Re-run EQPT under a separately bounded authorization. Attempt AMC and GMM only after EQPT normalizes and replays deterministically.
5. Let the registered account snapshot workflow capture both accounts on every August 24–September 4 date. Confirm each scheduled run succeeds and preserve the artifacts.
6. If all four engineering cases eventually replay exactly, preregister a behavioral comparison or threshold hypothesis before inspecting outcomes. Do not tune by case.
7. Complete the larger representative walk-forward and prospective paper sequence before any policy-promotion or profitability interpretation.

## Still not ready

- No full portfolio backtest is complete.
- Only one real-data feature case has completed; EQPT stopped at normalization and AMC/GMM remain untested.
- No hidden-buyer, hidden-seller, tape-exit, or Level 2 entry threshold is selected.
- No representative multi-regime feature validation, consolidated multi-venue book, live capture/reconnect path, calibrated queue/impact model, or full broker integration exists.
- The complete Ross setup-family inventory remains unfinished.
- No exact Ross Cameron imitation or comparable-profitability claim is valid.
- AI remains shadow-only, paper accounts remain research-only, and live-money trading is out of scope.

## What is needed from the owner

Nothing is needed to test the unarmed code or to let the scheduled account snapshots run, beyond keeping both paper accounts flat and unreset. Publishing this unarmed bundle requires explicit authorization. Any future Databento attempt requires a second, separate authorization after the unarmed parent is published.

## Verification

- Unarmed aggregate Fill/Cancel classifier: 8/8 focused tests pass.
- No Databento request was made while preparing this classifier.
- Complete repository suite: 680/680 tests pass.
