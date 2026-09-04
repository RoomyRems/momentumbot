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

The v0.6 child repaired the float-stage identity vocabulary and run
`33521937708` completed all 30 float dates and all 946 candidates with zero
candidate rejection. It then permanently failed before news provider access:
the unchanged news builder reloaded the valid float bundle through the legacy
validator, which rejects `unique_cik_fallback`. v0.6 is consumed and may not be
rerun. Its terminal cumulative ledger is 17,540 of 40,000 requests: 363
Massive, 15,849 Alpaca and 1,328 SEC.

The retained v0.6 checkpoint contains 584 normalized source files,
542,222,230 bytes, 30 dates, 946 candidates and 946 complete float records.
The v0.7 downstream compatibility repair failed safely before consumption in
run `33530672018`; its opaque four-request metadata check was replaced by the
v0.8 single-fetch, field-specific validator. v0.8 then ran once as run
`33543415600`. Its authorization, exact commit/tree, environment and both
45-test gates passed, and the validator failed closed at the parent artifact
`digest` field before checkpoint download, consumption or provider access.

The exact root cause is a preregistration transcription error. v0.8 froze
`ab51a247...3d469c35`, while both GitHub's live metadata and the independently
downloaded, archive-verified ZIP hash to
`ab51a247d4fc86b61d0099087721987b704def9d1086c6cdafb7767d63fa8b6e`.
No v0.8 tag or run artifact exists and the inherited request ledger remains
17,540 of 40,000. v0.8 may not be rerun.

v0.9 was published and dispatched once as run `33577895166`. It passed every
provider-free gate, permanently consumed its authorization, completed all 30
news dates, and failed during canonical scanner-source serialization on the
first candidate, BLRX. The exact-RVOL adapter emitted its intended 359-minute
grid while the raw candidate bars had 177 observed timestamps; the frozen
writer incorrectly required identical indexes before persisting the RVOL values
that the scanner already reads only at raw-bar timestamps. This was a
deterministic adapter contract mismatch, not a provider, credential, or budget
failure. The terminal ledger is 17,844 of 40,000 requests: 363 Massive, 16,153
Alpaca and 1,328 SEC.

v0.10 was published and dispatched once as run `33706372901`. Its validation,
consumption, and acquisition jobs succeeded. All 30 canonical scanner-source
dates completed, the exact-RVOL repair passed the prior v0.9 failure point, and
the 706-file provider checkpoint was uploaded with 30,522 of 40,000 requests:
363 Massive, 28,831 Alpaca, and 1,328 SEC. The separate credential-free freeze
job completed all 30 scanner snapshots, then failed in the final deep-replay
summarizer. That summarizer reloaded the valid float bundle after the scanner
adapter restored the legacy float validator, which accepts obsolete `cik` but
rejects 209 authoritative `unique_cik_fallback` identities. The failure was a
deterministic validator-scope mismatch, not a provider, credential, budget,
acquisition, or scanner-freeze failure. v0.10 is permanently consumed and may
not be rerun.

v0.11 was then installed and dispatched exactly once as run `33928334660`.
Its provider-free validation, immutable checkout, dispatcher check, exact
artifact-metadata check, and v0.10 checkpoint download succeeded. It failed
closed in the next step because the same shell step installed MomentumBot into
`.venv-v11` but invoked system `python` before the `GITHUB_PATH` addition could
take effect. The resulting `ModuleNotFoundError` occurred before checkpoint
deep validation, scanner output, or final replay. Provider calls remained zero,
the safe-failure artifact is `9957636441`, and v0.11 may not be rerun.

The registered provider-free repair is now v0.12. It invokes the explicit
`.venv-v12/bin/python` for that same-step comparison and adds a static workflow
regression for the exact failed form. Everything else remains inherited: exact
v0.10 provider-checkpoint artifact `9877181150`, all 706 source files, 30
scanner replays from canonical inputs, the 946-record identity preflight, the
narrow final-summarizer identity scope, and `finally` restoration. v0.12 has no
provider entrypoint or credential and authorizes zero additional provider HTTP
attempts. Candidate-bound Micro or Databento acquisition and transcript-label
review remain blocked until the label-blind source Snapshot succeeds.

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
