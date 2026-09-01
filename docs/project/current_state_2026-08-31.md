# MomentumBot checkpoint — 2026-08-31

## Current state

The prospective August 24–September 4 panel is terminally closed. Its five
attempted dates were operationally incomplete, the five remaining dates were
withdrawn before starting, and the public default-branch workflows are now
validation-only. The exact closure record is
`research/data-audits/prospective-panel-v0.1-closure-2026-08-31.json`.

The replacement `sealed-historical-walk-forward-v0.1` experiment is registered
provider-free against research parent `a2d2ffe`. It freezes an opaque eight-part,
2,292-record transcript commitment, a 66-date prior-research exclusion manifest,
and a deterministic 30-full-session block. Runtime has not started, transcript
record values have not been decoded for selection, and no provider authority is
granted by the registration.

## Active gate

Provider availability passed after the v0.2 Alpaca credential-routing repair.
Source acquisition v0.1 then failed safely at its 20,000-request ceiling.
The request-ceiling-only v0.2 child succeeded in GitHub Actions run
`33389380992`: 24,779 of 40,000 authorized attempts, 698,035,604 retained
bytes, zero incremental provider cost, and a complete independently verified
30-date bundle. Its permanent audit is
`research/data-audits/sealed-historical-source-acquisition-v0.2-run-33389380992-success-2026-08-31.json`.

The first provider-free scanner runtime gate then failed before Micro replay.
All 66,902 scanner rows reproduced exactly, but the frozen rank inputs compare
split-adjusted previous closes with raw intraday closes. Near-integer basis
ratios created impossible leaders and blocked every small-account top-three
activation even though 4,156 row-minutes across 25 dates passed its other
pillars. Zero small-account activations is therefore an invalid data result,
not strategy evidence. No provisional activation is frozen.

The v0.3 child failed after provider acquisition because its artifact validator
reconstructed adjusted gain from raw displayed price. The v0.4 child repaired
that mismatch and several adjacent recovery, float-basis, candidate-union and
checkpoint defects. Run `33468687163` completed all 30 normalized market dates
and permanently consumed v0.4, but failed during float enrichment. The v0.5
child added candidate-level containment and recovered the exact v0.4 source.
Run `33516311649` then failed on candidate `CHEB` because the consumed float
validator rejected the authoritative `unique_cik_fallback` identity kind while
admitting the obsolete name `cik`. This was a code-contract vocabulary mismatch,
not bad provider data.

The v0.5 failure checkpoint is complete through normalized market discovery:
523 files, 537,662,001 bytes, 30 dates and 946 candidates. Exact provider-free
replay validates every qualification-minute raw/split target pair and all 946
authoritative identities: 737 Composite FIGI and 209 unique-CIK fallback. The
child recovery must therefore reuse that tree without
repeating Massive, identity or market requests; request accounting starts at
the parent's 14,536 attempts.

The active local repair is v0.6. Before consumption it rehashes the exact v0.5
checkpoint and validates all 946 identities against only `composite_figi` and
`unique_cik_fallback`. Its float adapter consumes those exact names without
rewriting identity values and retains v0.5's candidate-level provider-data
containment. It then resumes unchanged float, news and canonical scanner-source
acquisition, checkpoints every pre-scanner byte, and freezes scanner snapshots
in a separate provider-free job. v0.6 is not published, authorized, consumed or
dispatched.
Candidate-bound Micro or Databento acquisition and transcript-label review
remain blocked.

The strategy scope freeze remains active: no new setup, AI authority, scanner or
Micro threshold change, account rule change, execution-cell selection, or
management-rule change is allowed inside this experiment.

## Legacy workflow hygiene

The v0.3 registration push also exposed two superseded provider workflows whose
path filters still matched shared scanner and historical-data tests. Runs
`33445164818` and `33445164899` reached legacy Alpaca calls and failed with HTTP
401 before producing usable data. They did not affect the v0.3 registration,
whose validation passed and whose acquisition job remained skipped.

`massive-historical-census.yml` and `causal-scanner-frozen-source.yml` are now
manual-only historical reproduction workflows. Ordinary pushes cannot start
their jobs, expose their provider secrets, or overlap the active sealed-source
experiment. This trigger-only maintenance does not change any provider route,
strategy policy, scanner/Micro threshold, frozen artifact, or acquisition
authority.
