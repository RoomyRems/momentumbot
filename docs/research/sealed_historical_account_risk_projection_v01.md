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
