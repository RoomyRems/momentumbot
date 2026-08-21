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
  tests only the preregistered session-boundary clear interpretation on EQPT.
  It requotes exactly two requests, downloads nothing above $0.02 or 15,000,000
  bytes, blocks reruns, retains the snapshot-clear path, resets both books on
  every later clear, uploads only a sanitized diagnostic, and creates no
  runtime authority. It is implemented and locally tested but has not issued
  a v0.2 provider time-series request.
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
- `research/data-audits/prospective-management-execution-v0.1-2026-08-20.json`
- `research/strategy/databento-microstructure-metadata-quote-v0.1.json`
- `research/strategy/databento-microstructure-smoke-acquisition-v0.1.json`
- `research/strategy/databento-microstructure-smoke-acquisition-v0.2.json`
- `research/strategy/prospective-management-execution-v0.1.json`
- `docs/research/databento_metadata_quote_v01.md`
- `docs/research/databento_microstructure_smoke_acquisition_v01.md`
- `docs/research/databento_microstructure_smoke_acquisition_v02.md`
- `docs/research/prospective_management_execution_v01.md`

## Active gates

1. Publish the one-shot v0.2 reset-repair child. Its push-triggered workflow
   must repeat the two free quotes below both hard ceilings before it downloads
   the EQPT MBO/MBP-10 pair, reconstructs, sanitizes, deletes the raw files, and
   uploads the G1/G2 diagnostic. A GitHub Actions rerun is explicitly blocked.
2. Retain both hash-bound pre-session account snapshots on every registered
   August 24–September 4 date. The credential prerequisite is complete.
3. Integrate the frozen management rule and both fixed execution scenarios only
   when the registered account snapshot and causal top-of-book/halt inputs
   exist. Missing quotes remain unavailable; there is no SIP-print fallback.
4. If v0.2 passes, inspect and permanently bind its sanitized artifact before
   deciding whether the preregistered four-case replication is justified. A
   v0.2 failure remains the result and stops without a retry.
5. Run the larger preregistered walk-forward and prospective paper sequence
   before any policy promotion or profitability interpretation.

## Still not ready

- No full portfolio backtest is complete.
- The v0.1 Databento time-series run failed before any real MBO-to-MBP-10
  comparison. The v0.2 reset interpretation remains unobserved against real
  data until its one-shot EQPT workflow completes.
- No exact Ross Cameron imitation or comparable-profitability claim is valid.
- No complete strategy-family, discretionary seller/tape, cross-account
  attention, consolidated Level 2, market-impact, or calibrated broker model
  exists.
- AI remains shadow-only, and no live-money trading is in scope.

## Verification

The previously published checkpoint passed its focused 31/31 tests and full
570/570 suite. The Level 2 parent, quote, and v0.1 acquisition verification
passes 26/26 focused tests. The v0.2 reset-repair bundle passes 11/11 focused
tests. The complete repository passes 592/592 tests, including both reset
modes, later-clear recovery, deterministic budget, cleanup, dual replay,
MBP-10 mismatch, provider/parser failure, sanitization, and one-shot workflow
checks.
