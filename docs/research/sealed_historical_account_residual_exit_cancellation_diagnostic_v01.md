# Residual cancellation-check failure diagnosis v0.1

The residual replay completed, but its independent checker rejected a valid
no-fresh-quote cancellation status. This document records a post-outcome
diagnosis of that specific failure. It does not certify the complete runtime,
repair the consumed checker, change execution policy or rerun the account replay.

## Preserved first attempts

Implementation `49e35b57f06b97a73590517b993de0e333d692dd`, tree
`d40fb307d9d918f1deb59c8a3351ef2efa985712`, and registration
`33ced4d6e2069f36a277b3b2025f38e07e2d7a3e9eeecd031345400ed6b54dae`
remain unchanged. The preceding published checkpoint is
`033fbe4bf7ae04c012d49e9d83d5657071c1be54`.

[Hosted run 34295994393](https://github.com/RoomyRems/momentumbot/actions/runs/34295994393),
job `102292641574`, attempt 1, finished on September 9, 2026 at 02:05:36 UTC.
The replay step succeeded and emitted the mandatory 12 paths and 360 session
slots. Independent verification then failed with
`ValueError: residual cancellation witness differs`. The run took about
85 minutes and did not reach its 120 minute timeout.

Artifact `10085178783` contains exactly three files: runtime, freeze manifest,
and attempt receipt. It contains no independent verification report. Its
1,119,624 bytes match ZIP SHA
`079bb67f53d4fe9151522d995c127da109c11e19d1a1638be3e53fffbdb0eb76`.
Direct download verified the inventory, CRC, canonical seals and runtime
inventory. The hosted receipt exactly matches the preserved local receipt.

Runtime content SHA is
`21bd9efa65c5c5776242bb9a6a53d28c134aefe31ed7da00d389402e29f3efba`;
its 10,602,145 bytes have file SHA
`90f5a02dacc26eec03e8aacb5758150c0efc8b6a9b56d9c1d4eb7f5d7287c716`.
Archive integrity establishes byte identity, not correctness of the replay.

The original local process is no longer present. Only its attempt receipt and
empty log remain; no runtime or checker report was produced. Its termination
cause was not logged and is not established. It was not restarted. Therefore
local/hosted runtime comparison remains unavailable.

## Source-proven cause

The defect is the frozen checker's two-way classification:

- A positive confirmed fill implies `partially_filled_cancelled`.
- Any zero-fill cancellation is assumed to be `cancelled_unfilled`.

The frozen execution model also distinguishes `unavailable_no_fresh_quote`
and `halted_cancelled`. Its unchanged feedback reducer retains that execution
status in the cancellation acknowledgement. A valid reference at submission
does not guarantee a fresh quote when the order arrives or while it is active.

Every one of the 27 residual authority/exhaustion acknowledgements has the
expected order ID, time and cancelled quantity. The status distribution is
15 partial cancellations, nine ordinary unfilled cancellations and three
no-fresh-quote cancellations. Only the last three contradict the narrow checker
predicate. They are DPRO on June 10, 2025, in the separate main/conservative
1, 5 and 10 second paths, each for two shares.

| Original event | UTC time / value |
|---|---|
| Last usable quote | 13:34:01.968300231 |
| Order decision | 13:34:01.984238739 |
| Order arrival | 13:34:02.084238739 |
| Cancellation acknowledgement | 13:34:02.434238739 |
| Quote age at decision | 15.938508 ms |
| Quote age at arrival | 115.938508 ms |
| Frozen maximum age | 100 ms |
| Eligible active quote candidates | 0 |

The original capture contains just one quote, and no later quote becomes
eligible before cancellation acknowledgement. Native quote/status evidence
therefore supports `unavailable_no_fresh_quote` with zero fills. The runtime
status is correct for these three records. This finding does not establish
that all other runtime checks would pass.

The missing local management ZIP was restored from original GitHub artifact
`10028253493`, verifying the exact 43,591,721 bytes and registered SHA
`e6ae822301440e3c0d183546b472e5b6f4e0f50d6e4f1b67178ba6bf46e382e0`.
The unchanged verifier then reproduced the same hosted failure locally.
No market-provider request or historical replay was performed.

## Reproducible diagnostic and regression

`scripts/diagnose_sealed_historical_account_residual_exit_v01.py` requires the
exact failed runtime and original source archives. It first reproduces the
frozen checker failure, enumerates every residual cancellation, and reconstructs
native quote eligibility for each mismatching no-quote status. It independently
checks the arrival age, half-open active interval, status timing and original
capture bounds. It emits a diagnostic report, never an acceptance report.

The [diagnostic evidence](../../research/data-audits/sealed-historical-account-residual-exit-v0.1-cancellation-diagnosis.json)
preserves each affected entry, order, acknowledgement and native source witness.
Its content SHA is
`138669a5fb265bad605995b4186755822aa7c4b1f5fe4810b048cc361196382d`.

Ten new tests include synthetic reproductions under both frozen execution
policies: the existing engine correctly generates the no-quote acknowledgement
and the original checker rejects it. Boundary tests cover exact quote age,
arrival, cancellation acknowledgement, halted and unknown status, equal-time
status changes, unusable quotes and changed capture bounds. An ordinary
zero-fill cancellation is checked separately. The original 36 component tests
are retained. Exact validation results and draft diagnostics are recorded in
the [failure audit](../../research/data-audits/sealed-historical-account-residual-exit-v0.1-verification-failure-diagnosis.json).

All 2,299 local tests passed with zero skips (277.807 seconds). The 46 focused
tests passed normally (8.837 seconds) and optimized (9.049 seconds), with zero
skips. Static checking found no undefined globals or production implementation
imports in the diagnostic entrypoint.

## Required next correction

Register a separate verifier-only child against this exact stored runtime and
the immutable failed checker. Reconstruct the zero-fill status from the native
active quote lifecycle, distinguishing no fresh state, all-halted states and
ordinary unfilled cancellation. Do not replace the predicate with an unchecked
status allowlist. Preserve exact order, timing, quantity, residual authority,
liquidity, waiting, risk, accounting and parent-prefix checks.

Run that separately frozen verifier against the stored runtime before deciding
whether another account replay is required. Preserve any additional failure.
The missing local runtime remains a separate reproducibility gap requiring an
explicitly preserved reproduction attempt; it must not be silently replaced.
Financial evaluation, account-backtest completion, retrospective labels,
overnight execution and promotion remain closed. Ross attachments are unopened.
