# Replay-verifiable account-state producer v0.1

This isolated child of `dcf1bc47b586653f3c0c97a4e433b4bdf1fff32a` derives
account checkpoints from approved seeds and recomputed executions. Its one
hypothesis is that deterministic execution replay can verify account-state
production while preserving capital and unresolved state across sessions.
It pins the completed fee/reconciliation freeze and 56 ancestor files. Frozen
policy, fees, source identities and parent implementations remain unchanged.

## What is implemented

`replay_path` accepts an externally committed synthetic source program with all
30 session slots and a nonempty chronological prefix. It starts each path from
the approved $30,000 main or $2,000 small seed exactly once. Callers cannot
provide balances, a prior close or a pre-entry ledger. Every later opening is
derived from the preceding checkpoint. `verify_path` independently receives
the program and claimed-result commitments, reruns the entire prefix and
requires exact agreement with every intermediate runtime and close.

The frozen position scheduler's bar, SIP-print and public feedback ordering
is routed through the fee/account reducer. Entries and confirmed sells update
cash, shares, daily fees, net realized P&L and the unchanged net risk guards.
The full bar and trade streams are verified even after the shares become flat.
The fee book persists between positions in the same session.

Verified flat cash carries to another session. Daily guards and fee accrual
restart using that carried capital; cumulative net realized P&L, fees and
campaign history are retained. USD amounts keep two to nine fractional digits.
Fractional cents are never rounded merely to fit the older transport contract.
An exact-cent compatibility envelope is emitted only when every amount fits.
If the frozen float ledger cannot preserve a decimal opening balance, execution
is blocked and the original exact state survives.

Open positions have unknown equity until a causal valuation is supplied by a
later component. Confirmed cash, remaining shares, entry/sell cancellations,
unsubmitted intents and input failures remain explicit. Their unresolved state
blocks later execution; there is no implicit liquidation or daily reseeding.
Unavailable opportunity references remain in the evidence without an order.
An available but unprocessed opportunity prevents an empty session from being
treated as complete.

## Scope and remaining dependencies

This is a synthetic component replay. The replay proof establishes that a
balance follows from the committed program; it does not establish the market
origin of that program. Historical activation, historical producer provenance,
account-close eligibility and financial metrics remain false. The registration
preserves all 12 original paths, 360 slots, 12 seeds, 348 prior-close dependencies,
744 opportunity references and 162 unavailable references. Its metadata build
does not open original market tapes or run historical trading.

Position windows are consumed serially and completely. A later position must
follow the prior window; overlapping decisions are not reordered or rescued.
The next child must provide causal valuation of carried positions and continuous
account/order/scarcity integration, including actual risk-flatten execution.
Only after those dependencies and the original-source bindings are registered
can the 30-session historical account replay be activated.

No provider, brokerage account or retrospective Ross corpus is accessed by this
step. No historical P&L result, broker-statement equivalence or policy promotion
is claimed.

## Verification

The new tests cover carried profits and fees, fractional cents, partial shares,
entry and sell orders awaiting cancellation, midstream failures, unchanged
runner output, stress execution, daily guard reset, omitted/unavailable inputs,
source/result tampering, path chronology, write-once registration and direct
offline CLI execution.

Twenty synthetic vector programs contain 404 session checkpoints and 21
confirmed journal fills. Twelve programs traverse every empty session of every
registered account/horizon/scenario path. Eight others exercise money and
incomplete-state transitions. The independent stdlib checker recomputes fee
arithmetic, journal cash, share conservation, net guards and session carry. It
does not import production modules or independently simulate the market fills;
full source-program recomputation is performed by `verify_path`.

The [local audit](../../research/data-audits/sealed-historical-account-state-producer-v0.1-independent-verification.json)
records the full and focused test gates, commitments and retained development
failures. Published code `bacf662a0370601a02aec9ca345b4b424f676a06` passed all eight GitHub
checks on attempt 1. All 2,028 local tests passed with zero skips; the 144-test
focused group passed normally and optimized locally and in the dedicated hosted
job with zero skips. General hosted CI passed 2,028 tests with 73 optional-SDK
skips. Both downloaded synthetic evidence files are byte-identical to local
results. The [hosted audit](../../research/data-audits/sealed-historical-account-state-producer-v0.1-hosted-verification-34185273453.json)
records exact publication and artifact evidence.

## Artifacts and offline commands

- [Contract](../../research/strategy/sealed-historical-account-state-producer-v0.1.json)
- [Frozen metadata](../../research/runtime/sealed-historical-account-state-producer-v0.1/freeze-manifest.json)
- [Producer](../../src/momentumbot/research/sealed_historical_account_state_producer_v01.py)
- [Independent checker](../../scripts/verify_sealed_historical_account_state_producer_v01.py)
- [Focused tests](../../tests/test_sealed_historical_account_state_producer_v01.py)
- [Hosted workflow](../../.github/workflows/sealed-historical-account-state-producer-v01.yml)

```bash
PYTHONPATH=src:scripts python scripts/build_sealed_historical_account_state_producer_v01.py --verify
PYTHONPATH=src:scripts python scripts/build_sealed_historical_account_state_producer_v01.py --synthetic-vectors --output-root /tmp/new-account-state-vectors
PYTHONPATH=src:scripts python scripts/verify_sealed_historical_account_state_producer_v01.py --vectors /tmp/new-account-state-vectors/synthetic-vectors.json --output /tmp/new-account-state-vectors/independent-verification.json
```

The output directory must be new. The locked environment is shared with the
sealed execution-quote validation workflow. CI installs no provider authority
and runs both normal and optimized focused checks.
