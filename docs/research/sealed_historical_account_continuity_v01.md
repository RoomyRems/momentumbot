# Campaign re-entry and original-window continuity v0.1

This isolated child starts from the verified scheduler checkpoint
`6933ff419afb034f9509eaa0898c3467571e32d8`, tree
`506c78abbbd7d3cc1db32ace9baa9d63f2d08edd`, and pins 95 ancestor files.
The hypothesis is that flat campaign re-entry and replay-verified continuation
can preserve exact accounting and the frozen execution attempt ceilings.
All development evidence is synthetic. Ross actions, fills, transcripts and
retrospective labels remain prohibited runtime inputs.

## Re-entry behavior

The existing policy permits two accepted entries per campaign. A campaign keeps
its original activation identity. Its first accepted fill is a starter; a new
plan for the same activation can produce one re-entry after the position is
confirmed flat and every entry/sell cancellation is acknowledged. A third
accepted campaign entry is blocked. An unfilled order consumes no accepted
entry, but still reserves account capacity through cancellation acknowledgment.
A different original activation creates a different campaign, even when its
symbol is the same. One activation cannot identify different symbols.

Sizing, account risk limits, candidate priority, marketable limits, execution
latencies, quote freshness and participation use the frozen implementations.
An acknowledgment tied with a decision cannot free capacity for that decision.
Open positions, adds and known account locks still prevent another entry.

Each new accepted fill gets its own fill identity, cost basis, initial stop,
target and attempt state. Campaign gross P&L, fees, accepted fill history and
entry counters persist. One daily fee book and the net account guard persist
across entries. Confirmed sell liquidity identities also persist. The child
changes entry binding and campaign accounting; the inherited management and
sell execution methods are unchanged.

## Resumable checkpoints

`checkpoint_path` produces a checkpoint through an inclusive nanosecond cutoff
in the last session of a committed source-program prefix. Earlier sessions are
replayed completely from the once-only seed. The checkpoint contains confirmed
cash, shares, current cost basis, accrued fees, account guards, pending order
reservations, management state and hashes of processed source prefixes.
Private simulated outcomes and future fill prices are not exposed.

`resume_path` requires independent commitments to both the original source
program and checkpoint. It reconstructs the prefix and compares the entire
checkpoint before continuing the reconstructed reducer. It never imports a
claimed balance or serialized Python object. A complete resume must produce
the same result bytes as uninterrupted replay. A later checkpoint cutoff can
also be requested for successive handoffs.

Resumption preserves partial fills, target confirmation, active stops, pending
cancellations, consumed liquidity and the one-target/one-terminal attempt
history. A partial terminal exit cannot acquire another attempt by restarting.
Missing exit quotes preserve an unsubmitted intent. A source failure preserves
known account and order state and remains a failure after resumption.

## Scope and remaining dependencies

Continuation is confined to the original session and source windows. A position
remaining open when its window expires is explicitly `original_window_exhausted`.
The next session retains that position and remains blocked. A valuation mark
does not extend an execution window, liquidate shares, cancel an order, adjust
share units or authorize another terminal attempt.

This completes synthetic same-symbol re-entry and continuation within original
windows. It does **not** implement overnight trading or resolve missing evidence
outside those windows. The next historical registration must bind original
market and corporate-action evidence and retain expired-window positions and
unavailable valuations explicitly. Any new execution window or retry policy
would require its own isolated registration.

The original 12 paths, 360 slots, 348 prior-close dependencies, 744 opportunity
references and 162 unavailable references remain unchanged. Cross-account
attention remains unresolved; main and small account paths are independent.
Historical runtime, continuous historical account eligibility, account-close
evidence, financial metrics and policy promotion remain closed. No original
market tape, provider account, brokerage account or Ross attachment was opened.

## Verification

The independent stdlib checker recalculates campaign entry roles and counts,
per-entry basis, campaign totals, fees, cash, shares, net guards and reservations.
It compares checkpoint event/journal/source prefixes, target/stop state and
attempt ceilings against uninterrupted evidence. The primary verifier reruns
the complete source program. The independent checker does not independently
simulate every market fill or authenticate historical source provenance.

All 2,145 local tests passed with zero skips, and 213 focused tests passed
normally and optimized. The independent checker verified 26 cases, 379 session
checkpoints, 40 continuation checkpoints, 145 scheduler events and 51 confirmed
fills. The [local audit](../../research/data-audits/sealed-historical-account-continuity-v0.1-independent-verification.json) preserves the evidence and initial fixture failures.
Hosted verification follows code publication.

- [Contract](../../research/strategy/sealed-historical-account-continuity-v0.1.json)
- [Freeze](../../research/runtime/sealed-historical-account-continuity-v0.1/freeze-manifest.json)
- [Implementation](../../src/momentumbot/research/sealed_historical_account_continuity_v01.py)
- [Tests](../../tests/test_sealed_historical_account_continuity_v01.py)
- [Independent checker](../../scripts/verify_sealed_historical_account_continuity_v01.py)
- [Hosted workflow](../../.github/workflows/sealed-historical-account-continuity-v01.yml)

```bash
PYTHONPATH=src:scripts python scripts/build_sealed_historical_account_continuity_v01.py --verify
PYTHONPATH=src:scripts python scripts/build_sealed_historical_account_continuity_v01.py --synthetic-vectors --output-root /tmp/new-account-continuity-vectors
PYTHONPATH=src:scripts python scripts/verify_sealed_historical_account_continuity_v01.py --vectors /tmp/new-account-continuity-vectors/synthetic-vectors.json --output /tmp/new-account-continuity-vectors/independent-verification.json
```

Use the hash-locked validation environment and a new output directory. The
builder denies external I/O and provides no historical or provider-run mode.
