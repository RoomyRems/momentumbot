# Microstructure feature mechanics v0.1

## Result entering this child

Databento replication workflow `32437696613`, attempt 1, succeeded at commit
`0bf27c49411d14146b74b7a9696a4ef5c202b65f`. INTJ matched all 59 aligned
MBO/MBP-10 samples, AMC matched all 200, and GMM matched all 200. Combined
with the frozen EQPT parent, the four mechanically selected engineering cases
match 612 of 612 samples across two independent MBO replays and every MBP-10
price, displayed-size, and order-count component.

That result proves the reset and reconstruction mechanics across the small-to-
large activity spread. It does not show that any Level 2 feature predicts a
Ross trade, improves P&L, or generalizes outside the four engineering cases.
The exact run, artifact, raw-file hashes, safety result, and claim boundary are
permanently bound in
`databento-microstructure-replication-v0.3-run-32437696613-success-2026-08-20`.

## What this child adds

`microstructure-feature-mechanics-v0.1` freezes a provider-neutral,
threshold-free causal feature engine before any real-data feature output is
opened. It consumes only validated canonical depth and tape events. It neither
reads Ross labels nor changes Micro-v0.1, management, sizing, account, broker,
or execution policy.

The engine reports all three receive-time windows together:

- one second;
- five seconds;
- ten seconds.

Each window is start-exclusive and end-inclusive. The three horizons are
engineering coverage, not competing model cells. No result may select a
favorite horizon from the four reconstruction cases.

## Exact mechanics

The snapshot contains these measurement families:

1. Best bid, best ask, spread, and up to ten displayed levels per side, with
   exact size and order count.
2. Displayed depth imbalance as integer numerator and denominator components,
   avoiding floating-point or rounding ambiguity.
3. Add, cancel, fill, and modify flow by side. Cancellation is measurable flow,
   not evidence of intent or spoofing.
4. Same-price, same-side displayed replenishment. Later additions match prior
   in-window depletions in FIFO order and separate replenishment after an
   execution from replenishment after a non-execution removal.
5. Tape event count, shares, notional, and first/last/minimum/maximum price by
   buy, sell, and explicitly unknown aggressor side.
6. Distinct observed aggressive trade prices and their span. This is not called
   proof that every intervening book level was consumed.
7. Executed volume and first-to-last price progress as separate integer
   components. A high-volume/low-progress conflict may later be interpreted as
   a hidden-liquidity proxy, never as proof of an iceberg order.
8. When the chart setup supplies a causal breakout level, buy flow at or above
   the level, maximum and last progress, and post-cross selling below it. The
   engine does not decide whether the breakout “failed.”
9. A ten-level displayed-depth walk for each explicitly supplied hypothetical
   order quantity. It reports filled and unfilled quantity, worst price,
   notional, and rational average-price components without assuming queue
   position or hidden liquidity.

Every output is hash-fingerprinted. A clear resets book, flow, and tape history.
Snapshot records establish state but do not count as live additions. The merged
depth/tape input must stay receive-time ordered and within one provider, venue,
symbol, and point-in-time instrument. An incomplete book is unavailable. A tape
correction or cancellation makes the affected tape family unavailable rather
than silently retaining a potentially wrong signed total.

## Source boundary

The mechanics translate observable concepts from three source-explicit lessons:

- `HB1IbyuJ37s`, the November 10, 2025 Level 2 class, teaches the conflict
  between executed volume, displayed liquidity, and absent price progress as
  the basis for suspecting hidden buyers or sellers.
- `xGIa8Vg0PWM`, the August 5, 2026 strategy course, names persistent sellers,
  hidden sellers, red tape, false breakouts, and slowing buying as adverse
  evidence.
- `6P25hNn_H00`, the April 22, 2026 micro-pullback class, keeps the
  first-candle-new-high chart trigger as the baseline while treating stacked
  bids and green prints as discretionary context.

Transcript captions support the research specification only. Caption text,
Ross fills, recap judgments, future prices, and P&L are prohibited from the
feature runtime.

## What is deliberately absent

There is no large-seller threshold, imbalance cutoff, minimum tape speed,
replenishment threshold, hidden-buyer score, hidden-seller score, breakout veto,
entry anticipation, exit trigger, sizing multiplier, or AI judgment. XNAS.ITCH
remains single-venue Nasdaq depth rather than consolidated national Level 2.

The snapshot may later become structured evidence for a separately frozen
shadow policy. It currently has no runtime or order authority.

## Next bounded gate

The candidate real-data mechanics run is intentionally unapproved. It would
re-acquire only MBO for INTJ, EQPT, AMC, and GMM, run the frozen mechanics, and
retain only sanitized feature diagnostics. MBP-10 does not need to be purchased
again because all 612 reconstruction samples are already exact.

The previously observed exact four-case MBO quote is `$0.072135579586`. A future
one-shot contract may use a hard ceiling of `$0.08` and `80,000,000` billable
bytes, with no batch job, retry, raw-data publication, broker action, or policy
promotion. It requires a new explicit authorization before any Databento call.

## Verification

The focused mechanics suite covers hash binding, exact rational depth output,
displayed-depth walks, FIFO replenishment, unknown aggressor preservation,
correction fail-closed behavior, breakout context, snapshot/reset handling,
scope and clock enforcement, start-exclusive windows, bounded history, and
byte-reproducible snapshots.
