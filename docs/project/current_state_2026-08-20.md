# Current project checkpoint — 2026-08-20 child

This is the active routing checkpoint. It extends the immutable August 19
checkpoint at `docs/project/current_state.md`, file SHA-256
`0db0e6b6ef32e231cfdd5ac980f9b3317e9c582d2fd71df9cb0b20b066545b4f`.
The parent remains byte-for-byte unchanged because its checksum is bound by the
historical account diagnostic audit.

## Completed today

- Paper-account credential workflow run `32318197220` succeeded at runtime
  head `898f297816e828ccebaa495a2402384106c8157f`. The main and small accounts
  were distinct, active, clean, and matched $30,000 and $2,000 exactly. The
  sanitized artifact, ZIP, manifest, and source hashes are permanently recorded
  in `account-credential-validation-v0.1-run-32318197220-success-2026-08-20`.
  This was validation only; it did not create a registered session snapshot.
- Databento child `databento-microstructure-metadata-quote-v0.1`, content
  SHA-256 `1c9401e49d500c38715dd61c7f180e3eb868d71b9a28926caa4b399d335f45b1`,
  ran successfully in workflow `32418655472`. Its independently verified
  sanitized artifact quoted all 20 exact requests at a conservative total of
  $0.207468646765 and 379,772,560 billable bytes. All four point-in-time
  symbols resolved and all five schemas were available. The quote run called
  no time-series, batch, or live endpoint, persisted no raw market data, and
  spent no credit.
- Databento acquisition child `databento-microstructure-smoke-acquisition-v0.1`,
  content SHA-256
  `d4b38436ef3b5fc08e853b5205c34df930de8abe88ffd36979dcc0e4e166115c`,
  ran once in workflow `32427326070`. It requoted and downloaded all 20 exact
  files for $0.207468646765 and 379,772,560 billable bytes, then deleted every
  raw file and uploaded only the sanitized diagnostic. G1 and G2 failed because
  all four cases had one valid clear and zero `F_SNAPSHOT` clears; the v0.1
  predicate therefore left every book unready and aligned zero samples. No
  actual MBO-to-MBP-10 disagreement was observed, no retry ran, and actual
  billing remains unknown. The failure is permanently hash-bound.
- Corrective child `databento-microstructure-smoke-acquisition-v0.2`, content
  SHA-256
  `61b9ab6a0894a5a6871feda0236cdb9605f14b7ce13633c36dd1cffc4aa4de2a`,
  ran successfully in workflow `32435988929`, attempt 1, at commit
  `a89f0470e4387d016600cdf7beebd09ae25b3146`. Its independently verified
  sanitized report quoted $0.005820024014 and 10,810,592 billable bytes, then
  exactly matched all 153 aligned EQPT samples across both independent MBO
  replays and every MBP-10 price, size, and order-count level. The run preserved
  the snapshot-clear path, deleted both raw files, uploaded no licensed record,
  changed no strategy or broker path, and created no runtime authority.
- Replication child `databento-microstructure-replication-v0.3`, content SHA-256
  `d6aca7030155bbf9483e1b2c014481e31eaca5954b42155bbb8366b7501c7b07`,
  ran successfully in workflow `32437696613`, attempt 1, at commit
  `0bf27c49411d14146b74b7a9696a4ef5c202b65f`. Its six-request preflight was
  $0.182469338178 and 365,533,168 billable bytes. INTJ matched 59/59, AMC
  matched 200/200, and GMM matched 200/200 across both independent MBO replays
  and every MBP-10 component. Together with EQPT, the engineering cohort is
  exact on 612/612 samples. Raw DBN files were deleted and only one sanitized
  diagnostic was uploaded. Actual billing remains unknown.
- Feature child `microstructure-feature-mechanics-v0.1`, content SHA-256
  `b048e26fabd163d66297fa57faf011fbb50d9b69377101dbd04337a1cc1eab6a`,
  binds that v0.3 result and implements causal, threshold-free one-, five-, and
  ten-second measurements for spread/depth, displayed imbalance, book flow,
  replenishment, signed tape, observed trade-price sweeps, execution/price
  progress, breakout context, and displayed-depth slippage. Unknown aggressor
  state is preserved, corrections fail closed, incomplete books are
  unavailable, and every snapshot is deterministic and hash-fingerprinted.
  The four engineering cases selected no window or threshold.
- Feature-diagnostic child `databento-microstructure-feature-diagnostic-v0.1`,
  content SHA-256
  `996e987f04cd14a87eb8ad56b5dfce9c84fcfbef1bc3af7b44919be0ec00e180`,
  freezes the exact four MBO-only requests and a deterministic XNAS
  `Trade → Fill → Cancel` adapter around that engine. The bundle is unarmed:
  its execution-authorization file is absent, its workflow listens only for a
  later exact authorization child, and no Databento call or credit use occurred.
  A future one-shot remains capped at $0.08 and 80,000,000 billable bytes and
  may retain only sanitized counts, availability totals, and digests.
- Prospective child `prospective-management-execution-v0.1`, content SHA-256
  `14812b9f25b5ea7230254ed86b1e0eaa30fffe3dc13b1ee141b19770706090f9`,
  freezes `half-2r-breakeven-first-red-1m` from source-explicit teaching, not
  July P&L. It records that this was not the least-negative July main-account
  cell. The provider-neutral L1 simulator implements marketable-limit direction,
  fixed receive-time latency and quote age, spread, one-use displayed-size
  haircuts, whole-share partial fills, cancellation acknowledgement, halt/resume,
  unavailable states, and account-day SEC/TAF/CAT fee aggregation.
- The primary and stress execution assumptions are both fixed and must be
  reported on identical opportunities. Neither may be selected because it
  looks better. The mechanics are uncalibrated and unintegrated, create no
  broker order, and cannot replace missing causal quote inputs.

## New provenance

- `research/data-audits/account-credential-validation-v0.1-run-32318197220-success-2026-08-20.json`
- `research/data-audits/databento-microstructure-metadata-quote-v0.1-2026-08-20.json`
- `research/data-audits/databento-microstructure-metadata-quote-v0.1-run-32418655472-success-2026-08-20.json`
- `research/data-audits/databento-microstructure-smoke-acquisition-v0.1-registration-2026-08-20.json`
- `research/data-audits/databento-microstructure-smoke-acquisition-v0.1-run-32427326070-failure-2026-08-20.json`
- `research/data-audits/databento-microstructure-smoke-acquisition-v0.2-registration-2026-08-20.json`
- `research/data-audits/databento-microstructure-smoke-acquisition-v0.2-run-32435988929-success-2026-08-20.json`
- `research/data-audits/databento-microstructure-replication-v0.3-registration-2026-08-20.json`
- `research/data-audits/databento-microstructure-replication-v0.3-run-32437696613-success-2026-08-20.json`
- `research/data-audits/microstructure-feature-mechanics-v0.1-2026-08-20.json`
- `research/data-audits/databento-microstructure-feature-diagnostic-v0.1-registration-2026-08-20.json`
- `research/data-audits/prospective-management-execution-v0.1-2026-08-20.json`
- `research/strategy/databento-microstructure-metadata-quote-v0.1.json`
- `research/strategy/databento-microstructure-smoke-acquisition-v0.1.json`
- `research/strategy/databento-microstructure-smoke-acquisition-v0.2.json`
- `research/strategy/databento-microstructure-replication-v0.3.json`
- `research/strategy/microstructure-feature-mechanics-v0.1.json`
- `research/strategy/databento-microstructure-feature-diagnostic-v0.1.json`
- `research/strategy/prospective-management-execution-v0.1.json`
- `docs/research/databento_metadata_quote_v01.md`
- `docs/research/databento_microstructure_smoke_acquisition_v01.md`
- `docs/research/databento_microstructure_smoke_acquisition_v02.md`
- `docs/research/databento_microstructure_replication_v03.md`
- `docs/research/microstructure_feature_mechanics_v01.md`
- `docs/research/databento_microstructure_feature_diagnostic_v01.md`
- `docs/research/prospective_management_execution_v01.md`

## Active gates

1. Retain both hash-bound pre-session account snapshots on every registered
   August 24–September 4 date. The credential prerequisite is complete.
2. Integrate the frozen management rule and both fixed execution scenarios only
   when the registered account snapshot and causal top-of-book/halt inputs
   exist. Missing quotes remain unavailable; there is no SIP-print fallback.
3. Publish the unarmed four-case feature-diagnostic bundle without its absent
   execution-authorization child. A later separately authorized one-shot may
   re-acquire only the four exact MBO streams below $0.08 and 80,000,000
   billable bytes. It must not redownload MBP-10, retry, retain raw data, or
   select a best window/threshold.
4. Run the larger preregistered walk-forward and prospective paper sequence
   before any policy promotion or profitability interpretation.

## Still not ready

- No full portfolio backtest is complete.
- The four Databento engineering cases reconstruct exactly, but no real-data
  feature snapshot, feature threshold, behavioral comparison, or economic
  result exists. This remains engineering evidence, not profitability evidence.
- No exact Ross Cameron imitation or comparable-profitability claim is valid.
- No complete strategy-family, discretionary seller/tape, cross-account
  attention, consolidated Level 2, market-impact, or calibrated broker model
  exists.
- AI remains shadow-only, and no live-money trading is in scope.

## Verification

The previously published checkpoint passed its focused 31/31 tests and full
570/570 suite. The Level 2 parent, quote, and v0.1 acquisition verification
passes 26/26 focused tests. The v0.2 reset-repair bundle passes 11/11 focused
tests. The v0.3 replication bundle passes 9/9 focused tests. The feature
mechanics bundle passes 9/9 focused tests. The unarmed four-case feature
diagnostic passes 11/11 focused tests. The complete repository passes 621/621
tests, including both reset modes, later-clear
recovery, deterministic budgets, all-three-case replay, cohort-preserving
mismatch, cleanup, dual replay, MBP-10 mismatch, provider/parser failure,
sanitization, one-shot workflow checks, exact rational features, bounded rolling
windows, replenishment matching, correction handling, atomic XNAS
`Trade → Fill → Cancel` ordering, inert execution authorization, and unavailable
states.
