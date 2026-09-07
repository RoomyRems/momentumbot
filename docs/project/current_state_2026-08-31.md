# MomentumBot checkpoint — 2026-08-31

## Latest continuation — 2026-09-06

Final source-freeze run `34039993297` and artifact `9993250947` passed independent
verification. The source tree, all 30 dates, 946 candidate/float identities,
and original 30,522-request ledger are frozen. The provider-free scanner plan
then froze 192 activations across 170 symbol/date pairs. Its exact output is
`research/runtime/sealed-historical-scanner-activation-v0.2/`.

The user's continuing development and operational authorization was applied to
the separate bounded SIP-print and prior-warmup capture. Code commit
`46e5bd28bf852402faf0e5092d1ca253ca6cc7d0` passed CI and dedicated validation;
sole execution child `5cab2eb3aa2b73a2cbf1d57575519a7b99961e24` started run
`34053730042`, attempt 1. Its consumption artifact `9995333130` was durably
uploaded before market-data access. Do not rerun or edit that consumed capture.

Input review identified one additional dependency: the canonical scanner stream
retains minute close/volume, while unchanged session VWAP also requires high
and low. A separate 170-request raw minute supplement is registered and tested
under `docs/research/sealed_historical_micro_session_inputs_v02.md`. It has its
own 680-attempt ceiling, consumption ref, and ledger; its execution file is
not part of the code preparation commit. The source Snapshot and both frozen
strategy profiles remain unchanged. Micro cannot execute until both captured
artifacts are independently verified and their minute fields and warmup basis
validate against the immutable source. No retrospective input is opened.

The raw minute supplement subsequently completed as run `34054580516`, attempt
1, at `bf5863a7115abef9e22c4f527448cd9c20084f47`. Independent verification passed
for capture artifact `9995587996`: all 348 files, 170 tapes, and 29,405 usable
minute closes/volumes match the immutable source, with 170 new child-ledger
requests and zero blocked attempts. The existing completed-bar cutoff excludes
149 hashed tail bars that become available at 10:00. The SIP-print/warmup run
`34053730042` remains the pending input dependency at this checkpoint.

The SIP-print/prior-warmup capture subsequently completed as run `34053730042`,
attempt 1. Independent verification passed all 688 files, 340 tapes and
receipts, 20,048,752 normalized rows, the exact 340-request plan, 2,264 provider
attempts, and zero blocked attempts. The captured evidence covers all 170
symbol/date pairs and 30 dates. Its ZIP commitment is
`d31eac851c1246ce23025e9518562ed3f41b8f818d42b8de707a6d86d307be99`.
The original v0.13 ledger remains untouched.

The provider-free Micro-v0.1 historical adapter is registered under
`research/strategy/sealed-historical-micro-runtime-v0.1.json`. It validates
both exact capture artifacts and the final Snapshot, normalizes the prior
split-adjusted warmup onto the raw session basis using only completed
preactivation pairs, and reuses the unchanged support, SIP aggregation, and
trigger builders. It writes explicit trigger/no-trigger outcomes and rejects
missing inputs. Account/order simulation, retrospective evidence, backtesting,
and policy change remain outside this stage.

That runtime completed once across all 30 sessions. It preserved all 192
activations and emitted 109 unique causal Micro decisions from 48 triggered
activations; 144 activations are explicit no-trigger outcomes and none are
unavailable. The immutable 31-file bundle is under
`research/runtime/sealed-historical-micro-v0.1/`, with manifest content hash
`cca8dbf0fcf37dd05dc77355de06bf384f37c081152302ce750c939550100904`.
The next causal dependency is candidate-bound execution and status input
registration. No account/fill simulation or backtest has begun.

The provider-free historical execution/status input registration now binds that
exact Micro checkpoint (`3d20c7efdcb53b8d3bfa46b550d41001108a8dac`) and re-derives
109 opportunities across 45 symbol/date pairs. Its 90 unquoted `XNAS.ITCH`
`mbp-1`/`status` requests use the unchanged 100-millisecond lookback and
550-millisecond tail with a one-nanosecond exclusive-end pad. All 30 dates,
including five explicit no-decision dates, and both profile eligibilities are
preserved. The three-file plan is frozen under
`research/runtime/sealed-historical-execution-input-plan-v0.1/`.
The next dependency is its own tested historical metadata-quote adapter and
exact one-shot record: at most 180 size/cost calls, followed by a successful
quote-bound bounded acquisition. No quote, acquisition, account/fill simulation,
backtest, or policy change occurred during registration. See
`docs/research/sealed_historical_execution_inputs_v01.md`.

The historical execution metadata-quote harness is now prepared under
`docs/research/sealed_historical_execution_quote_v01.md`. It preserves the
exact 90-request plan and permits only 180 size/cost metadata calls through a
bounded pinned-SDK transport. Its code push validates offline; a separate sole
execution record can consume the operation only after exact-parent CI and
dedicated validation pass. The consumption artifact must be durable before
provider access. No quote has executed in this preparation checkpoint.

The quote subsequently completed once as run `34066187628`, attempt 1, at
`dd295304dcc5e7cc0ebd300d094ab20636a72b92`. Independent verification passed both
ZIPs and all 16 files, including all 180 metadata/HTTP calls and zero blocked
attempts. All 90 requests have complete nonzero size quotes. The measured
ceilings are 154,456,640 billable bytes and USD `0.172787457709`. Result artifact
`9999061044` has ZIP SHA-256
`2a353b635407bffdb8076d88acdc520ad48f0bc19e28ff5d8c2e4ede8a88aa43`.
The exact report and independent audit are retained under `research/data-audits/`.
The next dependency is the separate bounded historical acquisition, with a
fresh complete re-quote at or below both ceilings before any download. Main,
all prior consumption refs, source/strategy evidence, and the original ledger
remain unchanged. No time series or account/fill simulation occurred here.

The separate historical execution-input acquisition is now prepared under
`docs/research/sealed_historical_execution_acquisition_v01.md`. Its fresh
180-call metadata preflight must stay within both verified quote ceilings
before any of the 90 exact time-series requests can begin. It reuses unchanged
record normalization and ordering validators, retains minimal normalized tapes
and sealed receipts, deletes ephemeral DBN files, and stops on the first
failure. Code validation and a separate sole execution child are required
before consumption; no acquisition execution record exists in this preparation
checkpoint. Downstream capture composition and management-input gates remain
separate from account/fill simulation.

That acquisition consumed its sole execution child
`5a375f86e951b1e9eeb6c010995c9b57025913b7` and ended in failure as run
`34067754001`, attempt 1. All 180 fresh metadata calls passed at the exact
original quote totals. The first time-series request, `2025-05-30-GITS-mbp-1`,
returned HTTP 200 and 21,788 bytes, then failed during normalization. The
remaining 89 requests were never attempted. There are zero completed
normalized tapes; the acquisition and downstream input gates did not pass.
This is an unavailable dependency, not a zero-trigger outcome.

Independent verification passed both retained ZIPs and all 23 metadata files.
The separate ledger is 181 attempts: 180 metadata and one time series, zero
blocked attempts. Result artifact `9999544369` has ZIP SHA-256
`90d9a52c04acbf3482a716e08ba4f66cb1e0a601ceb76fbb22de02a9ae424285`.
The original source ledger, main, all consumed refs, the 109 Micro decisions,
and every strategy/account assumption are unchanged. No account/fill simulation
or backtest began. The consumed acquisition has not been rerun or repaired.

The receipt identifies the normalization phase but does not retain the failed
subcheck. The temporary DBN was deleted under the registered retention rule,
so the exact metadata/mapping/order cause cannot be established from retained
evidence. A separately versioned diagnostic child is the next dependency;
validation must not be relaxed and the failed v0.1 remains immutable. The
completed monitor remains paused. See the permanent failure section in
`docs/research/sealed_historical_execution_acquisition_v01.md`.

The next diagnostic is now registered under
`docs/research/sealed_historical_execution_diagnostic_v01.md`. It binds only the
failed GITS request and permits at most two fresh metadata calls plus one
download, within that request's original byte/cost ceilings. It retains fixed
validation codes, exact metadata observations and a bounded typed projection
in original order while invoking the byte-pinned original validator. Diagnostic
evidence is explicitly ineligible for runtime input. Exact-parent code checks
and a separate durable consumption are required before execution. The original
90-request acquisition and its failure remain immutable.

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

The provider-free v0.12 repair invoked the explicit
`.venv-v12/bin/python` for that same-step comparison and adds a static workflow
regression for the exact failed form. Everything else remains inherited: exact
v0.10 provider-checkpoint artifact `9877181150`, all 706 source files, 30
scanner replays from canonical inputs, the 946-record identity preflight, the
narrow final-summarizer identity scope, and `finally` restoration. v0.12 has no
provider entrypoint or credential and authorizes zero additional provider HTTP
attempts. Candidate-bound Micro or Databento acquisition and transcript-label
review remain blocked until the label-blind source Snapshot succeeds.

v0.12 was dispatched once as run `33929860053`, attempt 1, at research commit
`dbe3abf2bf320fb014d76a34f3bf790d2d343deb` and main dispatcher
`070efdff977a637c60afff0b8826134ab31f92d4`. It validated the exact checkpoint
and completed all 30 scanner freezes, then failed in the final CLI because
`PARENT_REQUEST_BUDGET` was used without being imported. Only sanitized failure
artifact `9960256394` was uploaded; no final bundle or scanner checkpoint was
preserved by that execution. v0.12 remains failed and may not be rerun.

The additive v0.13 recovery fixes that runner import and adds an undefined-name
gate, actual CLI success/failure regressions, a pre-freeze ledger/identity
preflight, and a hash-bound intermediate upload before final reporting. Its
scientific commands deny network and subprocess I/O. A dedicated research-push
end-to-end verification workflow can produce a durable non-final proof against
the exact 706-file parent, unchanged 30,522-request ledger, all 946 identities,
and completed 767-file source. Verification reports cannot open the final gate.
The final v0.13 recovery was kept unarmed until that complete real-data proof
passed and the exact commit/tree/main dispatcher was separately authorized.

On 2026-09-06, final source-freeze run `34039993297` succeeded as
`workflow_dispatch` from `main`, attempt 1, dispatcher `de24eb17316191da69d92e61f6843af25e9c22d0`,
checking out research commit `8b2b9379319d293291366bae5f898f66c5dd492b`.
Independent verification matched both GitHub ZIP digests and every retained
source hash: 767 files, 190 directories, all 706 inherited files unchanged,
and only 61 permitted scanner additions. The exact 30 dates, both 946-identity
populations, pinned environment, and 30,522-request ledger remain unchanged.
The final report passes the source-acquisition gate; its intermediate remains
ineligible. Measured hashes and verification methods are recorded in
`research/data-audits/sealed-historical-source-v0.13-final-verification-34039993297.json`.

The v0.2 scanner/Micro preparation binds that exact final artifact and preserves
both scanner profiles and Micro-v0.1. Following the user's separate 2026-09-06
operational authorization, the scanner stage executed once and independently
verified 192 activations across all 30 dates and 170 symbol/date pairs: 164
general-profile and 55 small-account-profile activations, including 27 exact-time
ties. Its 31 frozen output files and permanent execution receipt are retained
under `research/runtime/sealed-historical-scanner-activation-v0.2/` and
`research/data-audits/sealed-historical-scanner-activation-v0.2-execution-2026-09-06.json`.

The candidate-bound Micro input child is prepared for 170 SIP-print windows and
170 prior seven-day one-minute EMA-warmup windows. It reuses the v0.13 session
bars and preserves the source ledger. Micro remains pending complete normalized
SIP inputs, derived completed 10-second bars, and causal warmup price-basis
validation; missing inputs cannot be treated as zero triggers. The next
one-shot execution child binds the tested acquisition commit/tree and workflow.
See `docs/research/sealed_historical_micro_inputs_v01.md`.

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
