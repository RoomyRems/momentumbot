# Historical account terminal continuation v0.1

## Current status: hosted success accepted without a local rerun

The user authorized proceeding without local reproduction. Hosted run
[34362104473](https://github.com/RoomyRems/momentumbot/actions/runs/34362104473)
finished successfully, including its original independent checker. Its exact
runtime and evidence are accepted under the separate
[hosted-acceptance amendment](sealed_historical_account_hosted_acceptance_v01.md).
All 360 slots executed, with 240 flat-complete and 120 flat-complete-with-unavailable-inputs
outcomes. No further local or hosted replay is required for that acceptance.

The 20 saved local records match the hosted prefix; the interrupted attempt
remains preserved and full cross-environment reproduction remains unverified.
The amendment does not change the original contract or execution rules, and
does not waive missing inputs or authorize financial/label evaluation. The next
development scope is unavailable entry-reference evidence. The status notes
below are historical and no longer mean the hosted run is active.

## Preserved observation before hosted completion

At the `2026-09-09T18:38:34Z` status check, the registered local attempt was
incomplete and its processes were unavailable. Executor sessions `56228`
(replay) and `12279` (verifier follower) both returned `Unknown process id`;
neither command appeared in the current process namespace. The saved progress
contains 20 of 360 session records, through index 19 of the first main-account
conservative path, last modified at `2026-09-09T14:26:34.792774+00:00`.
There is no final runtime, native failure envelope, verification attempt,
verification result or follower failure. Exit code, termination time and cause
are unknown. Automatic local verification cannot currently be relied on.

Hosted [run 34362104473](https://github.com/RoomyRems/momentumbot/actions/runs/34362104473),
job `102501424811`, attempt 1, still reports the replay step in progress at
implementation commit `0f057039e00480f3b0275d0bcd0bdabd23da7a96`.
Its independent checker and artifact upload remain pending. No artifact is
available; the job-log request returned 404 `BlobNotFound`. The status alone
does not establish intra-session progress. The frozen job timeout is 350 minutes.

The [status audit](../../research/data-audits/sealed-historical-account-terminal-continuation-v0.1-status-20260909T183834Z.json)
records these observations and binds a byte-verified archive of the local
receipt, all saved progress, logs and follower-start receipt. All 60 progress,
runtime and close content seals verify; this is integrity checking, not the
independent runtime check. The original
[execution-start audit](../../research/data-audits/sealed-historical-account-terminal-continuation-v0.1-execution-start.json)
and operational follower remain unchanged.

Preserve the hosted attempt through its terminal outcome, then inspect its
artifacts. The local attempt remains incomplete, and local/hosted comparison is
blocked. Do not restart either replay or infer resume authority from the saved
session records. Any recovery must preserve this original attempt and be
separately registered; no recovery replay was launched during this status check.

All seven other implementation workflows passed, including CI with 2,349 tests
and the existing 73 optional-SDK skips. Execution-checkpoint CI
[34363347527](https://github.com/RoomyRems/momentumbot/actions/runs/34363347527)
also passed. These checks do not establish historical replay completion.

This child tests one change: keep a terminal exit signal active after the
original two-order residual sequence, until confirmed shares are flat or the
original captured window expires. The accepted residual runtime and its
corrected cancellation verifier remain immutable.

## Frozen parent and diagnosis

- Parent commit: `998379812823ef44d2678cbca523ce73fbdf8bfb`.
- Parent tree: `a3281978c765fdf490fbad9ed92076cd9c602efb`.
- Accepted parent runtime content:
  `21bd9efa65c5c5776242bb9a6a53d28c134aefe31ed7da00d389402e29f3efba`.
- Completed reproduction registration:
  `25b2124138c419363176286e9bb8e209c210792365f00fc6ae4c6245a1742582`.

Inspection of the already verified mechanical state found the same blocker in
all 12 paths: positive confirmed shares, no pending order, and an acknowledged
`residual_budget_exhausted` event. The original source windows still had time
remaining. The session status `original_window_exhausted_with_unresolved_state`
describes the final unresolved result; these order sequences stopped at their
attempt ceiling before the window ended.

| Account/scenario, at each of 1s/5s/10s | First unresolved date | Symbol | Remaining shares per path | Seconds from last acknowledgement to original window end |
|---|---|---|---:|---:|
| Main / conservative | 2025-06-10 | DPRO | 2 | 776.255973951 |
| Main / stress | 2025-06-02 | INM | 60 | 919.031491959 |
| Small / conservative | 2025-06-18 | APVO | 1 | 942.918342220 |
| Small / stress | 2025-06-02 | INM | 6 | 919.031491959 |

This diagnosis used cancellation timestamps, remaining shares and source-window
bounds. It did not use later prices, financial results or Ross labels to select
a retry count or change any entry or exit threshold.

## Registered rule

1. Preserve the original first terminal and its single residual replacement,
   including all flags, fills, fees, source identities and consumed liquidity.
2. Once the second terminal cancellation is actually acknowledged with positive
   confirmed remainder, arm continuation. Every further partial or unfilled
   terminal cancellation follows the same rule.
3. Propose at the first eligible SIP print strictly after that acknowledgement.
   Submit all and only current confirmed, unreserved shares. The frozen terminal
   latch and stop/account-risk/red priority still apply.
4. Retain the frozen fresh, nonhalted quote requirement. An unavailable reference
   enters the original waiting mechanism; waiting does not spend an attempt.
5. Allow only one pending order. Arrival/cancellation latency, participation,
   marketable limits and the original common execution tape remain unchanged.
6. Require the existing 550ms tail plus an exclusive nanosecond to fit in the
   original window. Otherwise retain the unresolved state. No window extension,
   inferred liquidation or overnight execution is introduced.

There is no arbitrary third/fourth order ceiling or symbol-specific retry count.
The bound is the finite original stream/window and strictly advancing,
acknowledged order lifecycle. Targets retain their single-attempt ceiling.

Each continuation context links the actual prior submitted intent by hash, its
actual cancellation acknowledgement, the parent exhaustion event, and the next
terminal ordinal. Hash links avoid recursively embedding the entire order
history. A separate, entry-bound journal records ready, proposed, submitted and
expired transitions. A fully filled order cannot arm another continuation.

## Verification and execution

The isolated implementation uses the frozen waiting/native execution reducer.
The session finisher and independent account/path arithmetic remain exact
copies, enforced by AST regression tests. The child checker retains the corrected
source-based cancellation classifier and independently checks every additional
order's authority, current quantity, causal signal, earliest eligible print,
waiting evidence, lifecycle and window. Omitting the whole continuation journal
cannot conceal additional orders or acknowledged remainder.

The registration binds 299 parent files and five child implementation files.
Registration freeze:
`0f2570ba5b71783c3d27b47f2718217d7331bba8a2e8f7f09527c097fdf4a3fb`.
The original 12 paths, 360 session slots, 744 opportunity references and 162
unavailable references are retained. Each path still receives its original
capital seed once. All pre-continuation completed sessions and the first
two-order cancellation prefix must match the accepted parent runtime.

The CLI requires an external registration commitment before reading source
archives. It writes an exclusive attempt receipt, then fsynced session records
as progress evidence. These records are not a completed panel or restart
authority. A failed attempt keeps its receipt, completed session records and
failure evidence. One local and one hosted attempt are registered, with no
automatic retry; the hosted workflow rejects a rerun attempt.

Only the five original source archives and the original binding/runtime
artifacts may be used. Publication and full-suite validation precede historical
execution. Completion is recorded separately after both replay and independent
verification, including any failures or retained incomplete states.

No financial evaluation, Ross-label join, strategy promotion, new provider
request or broker action is authorized by this child. A successful mechanical
check does not itself complete the account backtest.

Prepublication validation passed 22 focused tests, 22 optimized tests and all
2,349 full tests with zero skips. Final registration checks also passed after
the workflow's trailing blank line was removed. All 299 parent pins were compared
directly with the parent commit. See the
[implementation audit](../../research/data-audits/sealed-historical-account-terminal-continuation-v0.1-implementation-verification.json).

See the [parent reproduction](sealed_historical_account_residual_exit_reproduction_v01.md),
[registration](../../research/strategy/sealed-historical-account-terminal-continuation-v0.1.json)
and [freeze](../../research/runtime/sealed-historical-account-terminal-continuation-v0.1/freeze-manifest.json).
