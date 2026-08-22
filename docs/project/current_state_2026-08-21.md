# Current project state — 2026-08-21

This checkpoint extends `docs/project/current_state_2026-08-20.md`. The August 19 and August 20 checkpoints remain immutable provenance. If a statement conflicts, this child controls only for work completed and independently verified after the August 20 checkpoint.

## Plain-English position

The project has now verified deterministic, threshold-free microstructure feature replay on all four mechanically selected Databento engineering cases: INTJ, EQPT, AMC, and GMM. INTJ passed under the instrument-event grouping repair; EQPT first isolated the Fill/Cancel identity mismatch and then passed under the published event-local repair; AMC and GMM subsequently passed under that same frozen repair and unchanged feature engine.

This is engineering evidence, not evidence that the trading idea is profitable or unprofitable. Exact five-field matches remain preferred, remaining Fill markers pair to Cancels by order ID and side within the completed per-instrument event, and the Cancel record's own payload supplies the canonical book removal. Every completed case reproduced its full feature-snapshot sequence exactly in an independent feature engine without selecting a feature horizon or threshold.

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

### EQPT repaired feature replay success

- Databento repaired-feature workflow `32520311940`, attempt 1, completed successfully at execution head `90fe2c2134127fa89c094b432ea97f4cba66199b`.
- Its single EQPT request requoted at `$0.002689146996` and `2,406,208` billable bytes, below the fixed `$0.003` and `3 MB` ceilings. Actual billing remains unknown.
- The repaired parser normalized 42,968 records into 29,159 per-instrument events and matched all 1,346 Fill markers to canonical Cancel removals.
- It produced 2,289 sampled feature snapshots and 13,734 fixed depth-walk scenarios. Signed-tape mechanics were available for every sample at the registered one-, five-, and ten-second windows.
- The independent feature replay matched exactly. No raw records, feature values, credentials, retrospective labels, thresholds, broker changes, or runtime authority were persisted.
- The permanent success audit is `research/data-audits/databento-microstructure-fill-cancel-repaired-feature-v0.1-run-32520311940-success-2026-08-21.json`, content SHA-256 `d87addf40a080d132799cb14daf8f6096b661d97369e7ebd9f8e216609cfffbb`.

### AMC/GMM repaired feature coverage success

- Databento coverage workflow `32544425875`, attempt 1, completed successfully at execution head `1f6407508a30b507754eb9ccaf7516e4398d6a7e`.
- The two-request preflight quoted `$0.069315630197` and `62,022,576` billable bytes, below the fixed `$0.07` and `65,000,000` byte ceilings. Actual billing remains unknown.
- AMC normalized 159,440 records into 108,103 per-instrument events, matched 11,456 Fill removals, produced 7,936 sampled feature snapshots, and evaluated 47,616 fixed depth-walk scenarios.
- GMM normalized 948,106 records into 794,192 per-instrument events, matched 51,053 Fill removals, produced 19,472 sampled feature snapshots, and evaluated 116,832 fixed depth-walk scenarios.
- Both cases reproduced their complete snapshot sequences exactly in independent feature engines. No retry occurred, and no raw records, feature values, credentials, retrospective labels, thresholds, broker changes, or runtime authority were persisted.
- The permanent success audit is `research/data-audits/databento-microstructure-feature-coverage-v0.2-run-32544425875-success-2026-08-21.json`, content SHA-256 `592a02b54fbaeb3182772905eb96fe50caba5c406e5aa79ee33218d8cb3c9ec5`.

## New unarmed development

`databento-microstructure-fill-cancel-repair-v0.1`, content SHA-256 `a5e8e0381e893610b641ce9a41d31138c1bde2134614efe7ebce725383b6abf0`, freezes the parser repair supported by the classifier result. It matches within the existing `(publisher_id, instrument_id)` / `F_LAST` event boundary, maximizes already-valid exact five-field matches, and then pairs remaining Fill markers and Cancels as a multiset by `(order_id, side)`.

The Fill marker remains book-neutral. A matched Cancel becomes the canonical Fill removal using the Cancel record's own payload. Extra Cancels remain Cancels, while a Fill without an order-ID-and-side match stops safely. This adds no feature threshold, case-specific value, provider call, runtime authority, strategy behavior, broker behavior, or execution authorization.

`databento-microstructure-fill-cancel-repaired-feature-v0.1`, content SHA-256 `b6b85967d420fca8262a399fc929c7308e79563db68a46acd17fd39186ad2e28`, binds the exact EQPT request to published repair commit `5db47089adc62a5df46fa85e41f3cc3eb26495c2` and the unchanged feature engine. Its workflow is inert because the future execution file is absent. A later separately authorized run would be limited to one first attempt, one request, no retry, and preflight ceilings of `$0.003` and `3,000,000` bytes.

`databento-microstructure-feature-coverage-v0.2`, content SHA-256 `1218c98f80cbf7c535636ddd67842ed6ebc0a39628eaababfc44a7a0b822e213`, froze the AMC and GMM continuation against the verified INTJ and EQPT exact-replay audits. Its separately authorized first attempt completed under the published Fill/Cancel repair and unchanged threshold-free feature engine. The resulting engineering coverage is now frozen; neither this workflow nor the earlier one-shot workflows may be rerun.

## Active gates, in order

1. Preserve the verified INTJ, EQPT, AMC, and GMM audits without rerunning any one-shot workflow.
2. Preregister one label-blind behavioral comparison or threshold hypothesis before opening any feature outcome values. Do not select a feature, horizon, threshold, or exception from these four cases.
3. Keep any future provider request behind a new frozen contract, exact cost gate, parent-bound authorization, and no-retry rule.
4. Let the registered account snapshot workflow capture both accounts on every August 24–September 4 date. Confirm each scheduled run succeeds and preserve the artifacts.
5. Use any later frozen behavioral artifact only as shadow evidence and integrate it with the existing prospective execution scenarios on identical opportunities.
6. Complete the larger representative walk-forward and prospective paper sequence before any policy-promotion or profitability interpretation.

## Still not ready

- No full portfolio backtest is complete.
- Four real-data engineering cases have completed under independently exact feature replay; representative behavioral validation remains unrun.
- No hidden-buyer, hidden-seller, tape-exit, or Level 2 entry threshold is selected.
- No representative multi-regime feature validation, consolidated multi-venue book, live capture/reconnect path, calibrated queue/impact model, or full broker integration exists.
- The complete Ross setup-family inventory remains unfinished.
- No exact Ross Cameron imitation or comparable-profitability claim is valid.
- AI remains shadow-only, paper accounts remain research-only, and live-money trading is out of scope.

## What is needed from the owner

Nothing is needed to preserve the four completed engineering results or to let the scheduled account snapshots run, beyond keeping both paper accounts flat and unreset.

## Verification

- Unarmed Fill/Cancel repair: 8/8 focused tests pass.
- Unarmed EQPT repaired-feature harness: 11/11 focused tests pass.
- AMC/GMM repaired-feature coverage and permanent success audit: 14/14 focused tests pass.
- EQPT and AMC/GMM repaired-feature workflows each completed on their authorized first attempt; no retry occurred.
- Complete repository suite: 720/720 tests pass.
