# Historical entry binding and management fill feedback v0.1

This isolated child binds checkpoint `75cacb70c9fc6fcc1465b5a3f65d991bad0b45bb`,
tree `e13b1249d76cdae67ab49468c5b922320d6b75f1`. Its single hypothesis is that
management of one accepted entry can conserve whole shares and move its stop
only after the intended target tranche actually fills. The implementation and
its tests use synthetic market evidence. No historical producer or runner is
enabled; no source tape, retrospective label, Ross transcript/action/fill,
provider, broker account, or financial result is accessed.

## Entry evidence

`bind_entry_evidence` requires caller-pinned context, a pre-entry ledger, and a
complete quote/status tape. The context binds the original opportunity, exact
account session slot, profile, availability reason, Micro decision, and stop.
It checks the original decision hash and plan identity, frozen account policy,
account identity and initial seed. An unavailable opportunity cannot pass.

The function copies the ledger, emits the original plan, computes the existing
maximum whole-share capacity at the conservative limit, reruns the unchanged
record-order L1 simulator, and applies the resulting positive fill through the
frozen account ledger. The returned receipt binds the actual filled quantity,
price, time, source request/ordinal, execution evidence, and unique accepted
ledger event. It cannot accept a caller-invented fill price or quantity. A
previous accepted entry for that symbol makes the multiple-entry/add case
explicitly unsupported. The caller's ledger is unchanged.

This is verification of mechanics, not authentication of the caller's historical
producer. Hashes supplied by a caller do not establish source provenance or a
valid preceding account close. The future registered runner must independently
verify the source artifacts, exact registered context, pre-entry account state,
ordering/scarcity, and producer commitments. No actual historical entry receipt
has been produced by this registration.

## Whole-share management

`ManagementFillFeedback` rebinds entry evidence in its constructor and accepts
original canonical SIP/bar envelopes. Completed bars retain original timestamp,
source order and ordinal lineage. Prints at or before the entry fill are
excluded; otherwise clean odd lots and existing condition rules are unchanged.
Original opportunity bounds, 15-minute signals and 60-second observation tails
remain unchanged. A merged source cannot extend an earlier opportunity.

The existing management cell remains `half-2r-breakeven-first-red-1m`. Necessary
execution translations are explicitly registered here, without examining
historical outcomes:

- The intended target tranche is `floor(confirmed entry shares / 2)`. A one-share
  position has no target order or breakeven move; its original stop/red exit
  remains available.
- An eligible target touch creates an intent, not a fill. The whole intended
  target tranche must be confirmed filled before the executable stop moves to
  entry. A partial target fill retains the original stop.
- Each position has at most one target attempt and one subsequent terminal
  stop/red attempt. Each uses the frozen marketable-limit policy with no
  automatic retry. A partial or unfilled terminal remainder stays explicitly
  open and unresolved. This bounded execution convention is not a claim about
  Ross's discretionary retry behavior or a completed production risk system.
- Stop/red signals observed during a pending target are latched. The pending
  order reserves its requested shares. Confirmed fills release sold shares;
  unfilled reservations persist until cancellation acknowledgment. A competing
  exit can be submitted only on a new eligible print after the pending order
  has cleared, for the actual remaining shares. A latched original-stop cause
  is not relabeled after a later target fill.
- All sells for a position require the same pinned complete quote/status tape,
  giving stable original source ordinals across attempts. Previously consumed
  quote liquidity cannot be spent again. A request alias or changed tape cannot
  bypass that check. The later exact exit acquisition must supply this common
  source; this registration invents no request list.

Both existing execution scenarios, tick, limit offsets, first-state participation
haircuts, native ordering and cancellation boundaries remain unchanged. Every
sell requires a fresh causal bid. Its fill uses the executable bid rather than
the SIP target proxy. Missing/ambiguous evidence raises an explicit input failure
and preserves the position; it is not a zero-trade or fabricated fill.

## Causal feedback clock

The reducer keeps the precomputed simulation outcome private until its fill
timestamp is reached. Its public pending order exposes only planned order and
latency/cancellation times. No future fill quantity or price changes position
state. A fill and a cancellation acknowledgment can each be applied only once.

Equal-time order is completed-bar signal, SIP prints in original source order,
then fill/cancel feedback. Thus a SIP print tied with a target fill cannot use
the resulting breakeven stop. Once equal-time feedback has been applied, a caller
cannot insert an earlier-phase market event. The runner must resolve a returned
intent at its exact decision clock before processing another event. Future
window prices cannot be used to submit an older intent.

These clocks retain the frozen SIP event-time and bar-close proxies. They do
not claim measured SIP receive times or bar-publication latency. A future
historical orchestrator must register and enforce the cross-stream merge and
account order lifecycle; the reducer is not that orchestrator.

Receipt and event hashes retain lineage. Sold plus remaining shares always
equal the accepted entry. Reserved shares cannot exceed the remaining position,
and target fills cannot exceed the fixed tranche. `closed_confirmed_shares`
describes position-share mechanics only. It cannot supply a verified account
close, cash balance, fees or financial metric. No end-of-window liquidation is
invented.

## Population and operation

The four metadata files retain the exact 109 opportunities, 86 available and
23 unavailable entry inputs, 30 dates, 12 paths, 360 sessions, and 744 references
(including 162 unavailable references). The $30,000/$2,000 once-only seeds,
preceding-session dependencies and all failed/consumed evidence remain intact.
All historical execution, management, account and financial-metric gates stay
false. Synthetic tests are not historical executions.

Registration: `research/strategy/sealed-historical-management-fill-feedback-v0.1.json`.
Metadata: `research/runtime/sealed-historical-management-fill-feedback-v0.1/`.
The CLI installs the external-I/O denial hook before importing research code.
It exposes metadata registration/build/verification only:

```bash
python scripts/build_sealed_historical_management_fill_feedback_v01.py --validate-registration
python scripts/build_sealed_historical_management_fill_feedback_v01.py --verify
```

`--build` writes only to an absent output. Verification reconstructs every byte;
rehashing a changed file cannot make it valid. Hosted validation uses the pinned
environment, read-only permissions, no secrets, and normal/optimized tests.

Next: register the historical entry/management runner and exact common exit
evidence scope. Independently verified source and account-state bindings remain
required. Historically applicable fees, causal next-session valuation, sell-ledger
reconciliation and continuous account replay are later integration dependencies.
The August 2026 fee defaults must not be applied automatically to 2025 sessions.
Any missing quote/status purchase needs its separately registered bounded gate.

## Local verification

All 1,820 tests passed in 98.382 seconds with zero skips. The 131-test focused
group passed normally (15.235 seconds) and optimized (15.718 seconds), including
53 new tests and 70 seeded synthetic paths across both execution scenarios.
Static undefined-global checks passed for the module and CLI. The primary
verifier reconstructed all four metadata files exactly.

The independent checker uses only the standard library, denies external I/O,
imports no project runtime, and independently verifies literal ancestor pins,
metadata bytes, all original windows/dates/session references, seeds, dependency
chains and closed runtime gates. It checks integer share arithmetic, pending
reservations, delayed breakeven and explicit terminal remainders against
[ten committed synthetic vectors](../../research/data-audits/sealed-historical-management-fill-feedback-v0.1-synthetic-vectors.json).
The registration freeze content commitment is
`3304832421b6a0ed963a93eba8fcbecaa85ebab6b77471bead7c16ff00c058d5`.

An earlier redirected full-suite log ended without a completion summary and is
not accepted as verification evidence. The completed run above captured the
process output before writing and hashing the final log. No code or policy was
changed to obtain that result. Initial local synthetic-fixture corrections and
unpublished metadata drafts are development evidence, not historical runs.
