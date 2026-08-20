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
  freezes 20 exact, ten-minute-aligned metadata/cost requests for the four
  Level 2 smoke cases. It pins `databento==0.83.0`, limits the future review
  ceiling to $12.50, sanitizes provider output, and contains no time-series,
  batch, live, or download call. The repository secret is reported configured,
  but the metadata workflow is unrun and no credits have been spent.
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
- `research/data-audits/prospective-management-execution-v0.1-2026-08-20.json`
- `research/strategy/databento-microstructure-metadata-quote-v0.1.json`
- `research/strategy/prospective-management-execution-v0.1.json`
- `docs/research/databento_metadata_quote_v01.md`
- `docs/research/prospective_management_execution_v01.md`

## Active gates

1. Publish the metadata-only Databento child and independently verify its
   sanitized exact-cost artifact. A passing G0 quote still does not authorize a
   data download.
2. Retain both hash-bound pre-session account snapshots on every registered
   August 24–September 4 date. The credential prerequisite is complete.
3. Integrate the frozen management rule and both fixed execution scenarios only
   when the registered account snapshot and causal top-of-book/halt inputs
   exist. Missing quotes remain unavailable; there is no SIP-print fallback.
4. If the Databento quote passes below $12.50, review one bounded four-case
   download separately before spending credits. Then test completeness and book
   reconstruction before any Level 2/tape feature receives shadow authority.
5. Run the larger preregistered walk-forward and prospective paper sequence
   before any policy promotion or profitability interpretation.

## Still not ready

- No full portfolio backtest is complete.
- No exact Ross Cameron imitation or comparable-profitability claim is valid.
- No complete strategy-family, discretionary seller/tape, cross-account
  attention, consolidated Level 2, market-impact, or calibrated broker model
  exists.
- AI remains shadow-only, and no live-money trading is in scope.

## Verification

Focused account, Databento, and execution tests: 31/31 passed. After preserving
the checksum-bound August 19 checkpoint and routing this child separately, the
full suite passed 570/570.
