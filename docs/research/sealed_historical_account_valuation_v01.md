# Causal next-session account valuation v0.1

This is an isolated child of the independently verified account-state producer
at `7840e5696fe8d2961ade913771f2c7cfa257493a`, tree
`df78ff3a64a2caf2ae93b95a56538b394964625d`. It pins 69 ancestor files and the
producer freeze `81fafc0a88ca1fcb5f74caf94f7aa55d557960b8f51f15334a4272adf71c594d`.
The hypothesis is that causal next-session marks establish equity anchors
without changing confirmed account balances, positions or order state.

## What is implemented

`value_next_session` first reruns the complete externally committed producer
prefix and checks its result. It values only the immediately following
registered session, at the frozen profile's **7:00 a.m. America/New_York**
strategy start. A caller cannot supply an arbitrary close, valuation time,
account balance or different session. A completed 30-session path cannot be
extended outside the registered calendar.

For each remaining long position, the mark uses the latest raw bid received by
the cutoff, preserving native receive-time/sequence order and original source
ordinal. A quote received exactly at the cutoff is known; a later quote is
excluded. The existing execution-scenario freshness limits apply: 100 ms for
conservative and 50 ms for stress, inclusive at the boundary. These are explicit
research valuation assumptions reused from the frozen execution policies.

The latest book must have positive sizes and a positive, unlocked, uncrossed
spread. There is no fallback to an earlier good book after a newer unusable
book. Status must be known and trading at the cutoff. Quotes sharing a receive
time with a status event are ambiguous, and a new book is required after the
latest status transition. A future quote, halt or reopening cannot influence
the current mark. The entire supplied source tape is still structurally and
cryptographically verified.

Share-unit continuity is a separate, explicit input. The synthetic fixture must
bind the preceding close, coverage time and known unchanged raw share units.
Missing evidence, an announced adjustment requiring transformation, or evidence
not yet known leaves the mark unavailable. The component never guesses split
ratios, adjusts position size or invents a cash adjustment. Historical
corporate-action provenance remains unverified.

## Accounting and continuation

Reference equity equals confirmed cash plus the marked value of remaining
shares. Original cost basis and opening unrealized P&L are retained separately
for the future continuous account reducer. Realized P&L and fees are already
reflected in cash: valuation neither realizes the mark nor subtracts fees again.
Amounts preserve fractional cents exactly.

A bid mark estimates equity. Actual proceeds still require executable fills;
displayed size does not establish that the whole position can liquidate at the
mark. No order, reservation, cancellation or fee accrual is created by valuation.

The continuation context retains all positions, pending orders, campaigns and
unresolved inputs from the replay-verified source state. Even if a pending
order's cancellation-acknowledgment time precedes the new session, valuation
cannot treat it as cancelled. Pending orders or unresolved blocking inputs
leave total equity unknown because the confirmed inventory is incomplete.
An available-but-unprocessed opportunity also remains blocking; an explicit
unavailable input remains visible without fabricating an order.

A verified flat, funded account can initialize the next session's empty frozen
ledger using carried capital. Open positions receive an opening valuation
anchor and an explicit execution blocker. Continuous scheduling, position
resumption, account-risk flatten orders and scarce-capital arbitration must be
implemented by the next child. This component does not import an open position
into an empty ledger or release capacity merely because its value is known.

## Registration and scope

The metadata maps all **348 preceding-to-next-session transitions** across the
original **12 paths and 360 slots**, preserving the original slot commitments.
Position-specific source requirements remain conditional on the replay-derived
inventory. This registration authorizes no source acquisition and opens no
historical market tapes, brokerage accounts or retrospective Ross datasets.

The implementation is verified with synthetic programs. Historical source and
corporate-action provenance, actual historical account-close evidence,
financial metrics and historical execution remain closed. The inherited
`next_session_open_position_valuation_verified` boundary refers to that
historical evidence; `account_valuation.valuation_complete` reports the result
for the supplied synthetic case.

Next: continuous chronological account/order/scarcity integration, followed by
original-source binding and historical activation. A missing historical
valuation source must remain an explicit input failure, never a seed reset or
an assumed closing price.

## Verification and artifacts

There are 36 new tests, including fresh/stale timestamp boundaries, future
information exclusion, native ordinal ties, unusable books, halt/resume status,
share-unit evidence, immutable pending orders, exact arithmetic, producer/result
tampering, all registered dependencies and direct offline CLI execution.
The independent stdlib checker verifies 29 synthetic cases, recomputes the
selected quotes and equity, and checks the source account arithmetic using the
frozen independent producer verifier. It imports no production module and does
not claim independent market-fill simulation or market-source authentication.

- [Contract](../../research/strategy/sealed-historical-account-valuation-v0.1.json)
- [Freeze](../../research/runtime/sealed-historical-account-valuation-v0.1/freeze-manifest.json)
- [Source](../../src/momentumbot/research/sealed_historical_account_valuation_v01.py)
- [Tests](../../tests/test_sealed_historical_account_valuation_v01.py)
- [Independent checker](../../scripts/verify_sealed_historical_account_valuation_v01.py)
- [Local audit](../../research/data-audits/sealed-historical-account-valuation-v0.1-independent-verification.json)
- [Hosted workflow](../../.github/workflows/sealed-historical-account-valuation-v01.yml)

Hosted verification is recorded after publication of the code commit.

```bash
PYTHONPATH=src:scripts python scripts/build_sealed_historical_account_valuation_v01.py --verify
PYTHONPATH=src:scripts python scripts/build_sealed_historical_account_valuation_v01.py --synthetic-vectors --output-root /tmp/new-account-valuation-vectors
PYTHONPATH=src:scripts python scripts/verify_sealed_historical_account_valuation_v01.py --vectors /tmp/new-account-valuation-vectors/synthetic-vectors.json --output /tmp/new-account-valuation-vectors/independent-verification.json
```

Use the hash-locked sealed execution-quote environment and a new output
directory. Registration, synthetic generation and independent verification
perform no provider calls.
