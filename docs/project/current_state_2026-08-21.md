# Current project state — 2026-08-21

This checkpoint extends `docs/project/current_state_2026-08-20.md`. The August 19 and August 20 checkpoints remain immutable provenance. If a statement conflicts, this child controls only for work completed and independently verified after the August 20 checkpoint.

## Plain-English position

The project has verified that the repaired Nasdaq order-event parser can turn one real Databento INTJ MBO case into deterministic, threshold-free microstructure feature snapshots. The first EQPT feature attempt then stopped safely because the frozen five-field Fill/Cancel identity was too strict. A separately bounded, aggregate-only EQPT classifier has now isolated and quantified that parser issue without persisting raw values: all 1,346 Fill records match Cancels by order ID and side, while 15 Fill records across 13 events do not match when price remains part of the identity.

This is engineering evidence, not evidence that the trading idea is profitable or unprofitable. The smallest supported repair is now implemented and unarmed: exact five-field matches are preserved, remaining Fill markers are paired to Cancels by order ID and side within the completed per-instrument event, and the Cancel record's own payload supplies the canonical book removal. The repaired EQPT feature replay has not yet been run.

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

### EQPT Fill/Cancel classifier success

- Databento classifier workflow `32512602607`, attempt 1, completed successfully at execution head `2ea5ffb6925fb8f045c6980eae5d0fec668ad1f2`.
- Its single EQPT request requoted at `$0.002689146996` and `2,406,208` billable bytes, below the authorized `$0.003` and `3 MB` ceilings. Actual billing remains unknown.
- The sanitized result recorded 29,159 events, including 1,020 Fill-bearing events with 1,346 Fill records and 1,382 Cancels.
- The exact five-field identity matched 1,331 Fill records and fully matched 1,007 events. The `(order_id, side)` identity matched all 1,346 Fill records and fully matched all 1,020 events.
- The difference is 15 coarse-only Fill matches across 13 events. Removing sequence and/or size did not improve overlap; within the registered projection lattice, price is the remaining differentiating field.
- The permanent success audit is `research/data-audits/databento-microstructure-fill-cancel-classifier-v0.1-run-32512602607-success-2026-08-21.json`, content SHA-256 `a1a4b72301f78b6c06811d810a15ecd830559d5db52dc9187ae00d8973fc983f`.

## New unarmed development

`databento-microstructure-fill-cancel-repair-v0.1`, content SHA-256 `a5e8e0381e893610b641ce9a41d31138c1bde2134614efe7ebce725383b6abf0`, freezes the parser repair supported by the classifier result. It matches within the existing `(publisher_id, instrument_id)` / `F_LAST` event boundary, maximizes already-valid exact five-field matches, and then pairs remaining Fill markers and Cancels as a multiset by `(order_id, side)`.

The Fill marker remains book-neutral. A matched Cancel becomes the canonical Fill removal using the Cancel record's own payload. Extra Cancels remain Cancels, while a Fill without an order-ID-and-side match stops safely. This adds no feature threshold, case-specific value, provider call, runtime authority, strategy behavior, broker behavior, or execution authorization.

## Active gates, in order

1. Publish the tested classifier-success audit and unarmed Fill/Cancel repair without an execution authorization file.
2. After that exact parent is published, register and separately authorize one bounded, aggregate-only EQPT repaired feature replay.
3. Attempt AMC and GMM only after EQPT normalizes and replays deterministically under the repair.
4. Let the registered account snapshot workflow capture both accounts on every August 24–September 4 date. Confirm each scheduled run succeeds and preserve the artifacts.
5. If all four engineering cases eventually replay exactly, preregister a behavioral comparison or threshold hypothesis before inspecting outcomes. Do not tune by case.
6. Complete the larger representative walk-forward and prospective paper sequence before any policy-promotion or profitability interpretation.

## Still not ready

- No full portfolio backtest is complete.
- Only one real-data feature case has completed; the repaired EQPT feature replay has not run, and AMC/GMM remain untested.
- No hidden-buyer, hidden-seller, tape-exit, or Level 2 entry threshold is selected.
- No representative multi-regime feature validation, consolidated multi-venue book, live capture/reconnect path, calibrated queue/impact model, or full broker integration exists.
- The complete Ross setup-family inventory remains unfinished.
- No exact Ross Cameron imitation or comparable-profitability claim is valid.
- AI remains shadow-only, paper accounts remain research-only, and live-money trading is out of scope.

## What is needed from the owner

Nothing is needed to test the unarmed code or to let the scheduled account snapshots run, beyond keeping both paper accounts flat and unreset. Publishing this audit and unarmed repair requires explicit authorization. Any future Databento attempt requires a second, separate authorization after the unarmed parent is published.

## Verification

- Unarmed Fill/Cancel repair: 8/8 focused tests pass.
- No Databento request was made while preparing this repair.
- Complete repository suite: 694/694 tests pass.
