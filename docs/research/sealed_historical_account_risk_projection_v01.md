# Historical account decimal risk projection v0.1

This isolated child of failed replay checkpoint
`9df7ad3487da1f2336701372703e4e5d196bd855` tests one hypothesis: exact confirmed
lot risk can pass the unchanged independent account checker without changing
orders, fills, fee accrual, timing, failed inputs or carry behavior.

The immutable parent runtime is
`28c745a20e6669a831ce6b9e09028e01a0c480bc1d88055c33b218ca9d88d56d`.
Its six stress paths report `(3.55 - 3.35) * 2` as
`0.39999999999999947` rather than exact decimal `0.40`. The original run,
registration, implementation, checker and failure audit remain unchanged.

## Isolated implementation

The child changes only the public reconciliation snapshot's campaign and
account open-risk fields. Each price is converted from its decimal string
before subtraction, then multiplied by confirmed integer remaining shares.
All lots are summed in a local 60-digit decimal context with inexact arithmetic
trapped. There is no cent quantization, epsilon or tolerance. The numeric JSON
projection must round-trip to the exact decimal value or it fails closed.
An already exact parent number keeps its original JSON representation.

The internal ledger, entry binding, sizing and acceptance methods are untouched.
The frozen scheduler reaches sizing only when the account is flat. Open shares
and unacknowledged orders reserve the sole position slot. Consequently, the
corrected public risk value cannot free entry capacity or increase an order.
This is a reporting precision repair, not a general conversion of the parent's
float entry sizing or acceptance arithmetic to decimal. Their boundary behavior
is deliberately outside this hypothesis.

A private child account overrides only snapshot projection. Its session adapter
inherits source resolution, scheduling and account execution. The session
finisher is copied from the pinned parent solely to construct that child; all
finisher arithmetic and nested component schema identities remain the parent's.
The outer registration and runtime identify this new experiment explicitly.

All original 30 dates, 109 opportunities, 12 independent paths, 360 slots, 744
references and 162 unavailable references are retained. Main/small seeds,
strategy, risk limits, fees, priority, source windows and order-attempt ceilings
remain fixed. The child's historical run is a new execution from the five exact
original archives, not an edit or postprocessing of the failed result.

## Independent verification

The stdlib checker uses rational arithmetic independently of the production
decimal calculation. It reconstructs remaining shares and basis from confirmed
journal fills, binds the active management stop, and checks each campaign as
well as the total. It then runs the unchanged parent chronology, accounting,
fees, net-guard, source, carry and population checks on all 12 paths.

A separate strict tree comparison with the byte-pinned failed parent permits
only public risk numbers and hashes of corresponding checked objects to change.
It checks all other values, including orders, entry evidence, pending intents,
attempt history, market progress and failure details. Changed hash strings must
resolve to corresponding object digests; arbitrary hash changes are rejected.
The unchanged parent checker also verifies the complete derived close chain.
This is not a second independent fill simulator.

Synthetic coverage includes nonbinary cent and subcent vectors, partial exits,
confirmed breakeven, multi-lot summation, exact JSON round trips, caller decimal
context independence and precision rejection. Integration coverage preserves
re-entry, account locks, fees, pending orders, failures and all empty paths.
One synthetic stress case must fail the old risk check and pass the child using
the very same unchanged checker. Nonrisk mutations and incorrect campaign or
aggregate risk are rejected independently.

Registration pins child code, checker, tests and workflow before original
source access. The offline builder retains an exclusive attempt receipt and
writes a fresh runtime directory. The hosted workflow verifies the same parent,
source archives, original binding and strict parity. Any failure stays frozen.

## Next gate and boundaries

The first parent's stale exit-reference failure remains expected. This repair
does not register waiting, a retry, a later quote at an earlier decision time,
an extended window or a liquidation. The next development gate is explicit
causal handling of an unsubmitted exit awaiting a fresh quote within the
original windows and existing attempt ceilings.

Financial evaluation, completed account-close evidence, retrospective comparison
and policy promotion stay closed. Ross attachments, fills, recaps and labels
remain unopened and prohibited from runtime. No provider or broker access is
part of this child.

## First original result: independent verification passed in both environments

Code `c93bafd7d28fb913734a6c552a3957586befe698`, tree
`5b238960f39dc73a0d49001f11e2bd070ef8dd8a`, was published before original source
access. Final registration freeze is
`87b1ab436d60df1bd6272d9e9f1975b0b728d0a1cd4f0badcab91957bffe46be`.
The development registration was preserved before removing only trailing blank
lines from the builder and workflow. Their stripped text was identical, and
the final registration was rebuilt and verified before publication. No
implementation or registration changed after original replay began.

All 2,223 local tests passed with zero skips. The 82-test focused group passed
normally and optimized with zero skips; all 23 new tests passed on their first
run. The new original runtime is
`5986950aab81652970a6318d93b7a6dd3b4b3384b8aa4a92d8578e3e985398e0`;
the independent report is
`0f8399c69c47abfb7ed9835f00689fe3e4886eaa0b05ab0ba452f6e09c901172`.

All 12 paths pass the unchanged parent chronology/account checks, rational
campaign/aggregate risk checks and strict parent parity. Six conservative path
objects are wholly byte-identical to their parents. Six stress paths now
publish exact `0.40` open risk. The 192 changed numeric fields comprise 12
snapshot risk fields and 180 repeated campaign risk fields across their
30-session carry chains. All nonrisk values and bound hash references pass
the independent comparison.

The result retains 12 entries, no sells, 12 first-session input failures and
348 blocked later sessions. All 744 references and 162 unavailable references
remain. Accounting verification passes; the historical backtest remains
incomplete because the stale exit-reference failure is unchanged. No
exit-waiting authority or completed account path is introduced.

GitHub run `34255076384`, job `102158687615`, passed on attempt 1 and produced
the identical runtime content commitment and independent report. Its 82 tests
passed normally and optimized with zero skips. CI `34255076369`, job
`102158687313`, passed 2,223 tests with the existing 73 optional-SDK skips.
All eight workflows passed on their first attempt. Main and all 16 consumed
references were rechecked unchanged.

The independent report text recovered from the hosted job log has exactly the
local file's 6,888 bytes and SHA-256
`fdbd89b1785ff82e63398358e66e475a856165416ceda2c3a7a1836ff6189a06`.
That [report](../../research/data-audits/sealed-historical-account-risk-projection-v0.1-independent-verification.json) and the
[verification audit](../../research/data-audits/sealed-historical-account-risk-projection-v0.1-local-and-hosted-verification.json) are retained in the repository.

## Remaining artifact comparison

GitHub artifact `10068241990` is reported as 926,951 bytes, ZIP SHA-256
`5298b020711a0681687f170dc78a313cfa03ba59bb5b38564c48e3795b1fe3ec`.
The artifact tool returned a download reference, but the executor disconnected
before the local download/inspection command could run:
`409 Conflict, environment_offline: Environment is not connected.`

Direct comparison of all four archive members with local files is therefore
**pending**, not claimed complete. Matching replay and report commitments, the
report text comparison, and all local/hosted checks are already verified. The
audit records this distinction explicitly. Finish the archive comparison when
workspace access returns, then register causal exit waiting within the original
windows and attempt ceilings. No strategy promotion or financial evaluation is
authorized by this result.
