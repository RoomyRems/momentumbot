# Current project state — 2026-08-21

This checkpoint extends `docs/project/current_state_2026-08-20.md`. The August 19 and August 20 checkpoints remain immutable provenance. If a statement conflicts, this child controls only for work completed and independently verified after the August 20 checkpoint.

## Plain-English position

The project now has verified engineering proof that its repaired Nasdaq order-event parser can turn real Databento MBO data into deterministic, threshold-free microstructure feature snapshots. INTJ completed successfully on the first authorized attempt. This resolves the specific parser failure recorded on August 20.

It does **not** prove that the features predict profitable trades, reproduce Ross Cameron's discretion, provide consolidated national Level 2, or generate realistic broker fills. No feature threshold or runtime trading authority exists.

The two Alpaca paper accounts are separately validated and the registered pre-session snapshot scheduler remains the most time-sensitive gate. It is scheduled for the ten registered market dates from August 24 through September 4 at 09:15 UTC (05:15 ET). The accounts should remain flat and their balances should not be reset during the study.

## Newly verified result

- Databento feature-repair workflow `32483408413`, attempt 1, completed successfully at execution head `d1c95d2208175864a56327cc78f0b0082eec6741`.
- The sole INTJ MBO request requoted at `$0.000130802393` and `117,040` billable bytes. Actual billing remains unknown.
- The sanitized result recorded 2,090 records, 1,700 per-instrument events, 61 within-event sequence transitions, and 238 sampled feature snapshots.
- The independent feature replay matched exactly. Signed-tape mechanics were available for all 238 samples at each registered one-, five-, and ten-second window; 1,428 fixed depth-walk scenarios were evaluated.
- No raw record, feature value, credential, retrospective label, threshold, strategy change, broker action, or runtime authority was persisted.
- The permanent success audit is `research/data-audits/databento-microstructure-feature-diagnostic-v0.3-run-32483408413-success-2026-08-21.json`, content SHA-256 `093f65e4d62b125e370d972a5bd9ee3880b5439d72072dd3fd533e4774d18ebb`.

## New unarmed development

`databento-microstructure-feature-coverage-v0.1`, content SHA-256 `0b098ea45120a1dd310dcf316c6ff31079ec1a5ca778bf078ca7698c03d6e18a`, freezes the remaining EQPT, AMC, and GMM MBO requests in their original mechanically selected order. It reuses the exact verified v0.3 repair and unchanged threshold-free feature engine.

The execution authorization file is absent. The workflow listens only for a future authorization-only direct child. This bundle therefore cannot call Databento or spend credit. A future run would require separate explicit authorization and would be capped at three requests, `$0.08`, and `80,000,000` quoted billable bytes, with one GitHub Actions attempt and no retries.

`strategy-discretion-coverage-v0.2`, content SHA-256 `e03c5130d36a075a274c0be9a504ca891307c271bf13b826f2af64fb0e217189`, updates five domains without changing the frozen v0.1 inventory. Level 2/tape, hidden-buyer mechanics, hidden-seller mechanics, and realistic execution are now described as partial deterministic research rather than wholly blocked or missing. Management remains partial shadow with newer artifacts recorded. All new authority remains research-only or shadow-only.

## Active gates, in order

1. Let the registered account snapshot workflow capture both accounts on every August 24–September 4 date. Confirm each scheduled run succeeds and preserve the artifacts.
2. Publish the tested unarmed feature-coverage and coverage-matrix bundle without adding an execution authorization file.
3. Only after the unarmed parent is published, decide whether to authorize the separate three-request Databento child under its fixed `$0.08` and `80 MB` ceilings.
4. If all four engineering cases have exact threshold-free feature replay, preregister a behavioral comparison or threshold hypothesis before inspecting outcomes. Do not tune by case.
5. Run the frozen management rule under both fixed execution scenarios only when registered account snapshots and causal quote/halt inputs exist.
6. Complete the larger representative walk-forward and prospective paper sequence before any policy-promotion or profitability interpretation.

## Still not ready

- No full portfolio backtest is complete.
- Only one real-data feature case has completed; the remaining three-case bundle is unarmed.
- No hidden-buyer, hidden-seller, tape-exit, or Level 2 entry threshold is selected.
- No representative multi-regime feature validation, consolidated multi-venue book, live capture/reconnect path, calibrated queue/impact model, or full broker integration exists.
- The complete Ross setup-family inventory remains unfinished.
- No exact Ross Cameron imitation or comparable-profitability claim is valid.
- AI remains shadow-only, paper accounts remain research-only, and live-money trading is out of scope.

## What is needed from the owner

Nothing is needed for the code-only bundle or the scheduled account snapshots beyond keeping both paper accounts flat and unreset. A future Databento run must receive a separate explicit authorization after the unarmed parent is published; until then the execution file must remain absent.

## Verification

- Frozen strategy coverage v0.1 plus v0.2 delta: 10/10 focused tests pass.
- Unarmed remaining-case Databento feature coverage: 11/11 focused tests pass.
- No Databento request was made while preparing this checkpoint.
- The complete repository suite passes 671/671 tests.
