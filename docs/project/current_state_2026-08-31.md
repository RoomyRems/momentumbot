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

The active repair is the provider-free registered v0.3 child source acquisition.
It changes only the historical price-normalization basis and then rebuilds
discovery and rank. Percentage gain and rank use split-adjusted prior and target
prices consistently; actual price and volume remain raw. It
must preserve all 30 dates, providers, thresholds and strategy/account rules;
it may not mutate or rerun consumed source v0.2. Candidate-bound Micro or
Databento acquisition and transcript-label review remain blocked.

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
