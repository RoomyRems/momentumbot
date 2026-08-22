# Microstructure behavioral comparison v0.1

## Purpose

This phase freezes the first behavioral use of the verified microstructure feature engine before any feature values or retrospective outcomes are opened. It asks a descriptive, label-blind question: on identical causal Micro-v0.1 first-candle-new-high opportunities, how do fixed post-trigger depth and tape measurements differ from the immediately preceding equal-length intervals?

The registration has no provider or strategy authority. It makes zero Databento requests, authorizes zero provider cost and bytes, does not select a representative cohort, and cannot submit an order.

## Paired clock

The anchor is the earliest provider receive-time instant at which the frozen Micro-v0.1 chart trigger is causally available. For every opportunity, all three horizons are reported together:

- one second: `(anchor - 1s, anchor]` versus `(anchor, anchor + 1s]`;
- five seconds: `(anchor - 5s, anchor]` versus `(anchor, anchor + 5s]`;
- ten seconds: `(anchor - 10s, anchor]` versus `(anchor, anchor + 10s]`.

The intervals are disjoint, start-exclusive, and end-inclusive. The breakout level comes from the same frozen chart plan. Microstructure cannot select the opportunity or rewrite the anchor or breakout level.

## Frozen measurements

The comparator reports exact post-minus-pre arithmetic for displayed depth imbalance, spread, signed tape, buy and sell executed shares, buy-side price progress, bid and ask replenishment after fills, bid and ask cancellation flow, causal breakout buy flow, and post-cross selling below the breakout. Exact rational inputs remain numerator/denominator components.

For order quantities supplied prospectively by the frozen execution plan, it also compares displayed filled and unfilled quantity, worst price, and notional across the same ten-level depth walk. It assumes neither queue priority nor hidden liquidity.

An increase, decrease, or unchanged label is only the sign of exact arithmetic relative to zero. It is not a fitted threshold, trade confirmation, veto, hidden-order classification, or policy rule. Unavailable source families remain unavailable.

## Claim and authority boundary

- All horizons and registered metrics must be retained; none may be selected because it looks favorable.
- Ross actions, recap language, P&L, later prices, and retrospective outcomes are prohibited from the comparison runtime.
- Single-venue XNAS depth is not consolidated national Level 2.
- The comparator cannot classify a hidden buyer, hidden seller, iceberg, spoof, false breakout, or trade quality.
- Micro-v0.1 entry, management, sizing, account, broker, and risk behavior remain frozen.
- Any future provider request requires a separate representative cohort contract, exact requests and cost caps, and a separately published parent-bound authorization.

## Next gate

Mechanically select and freeze a representative, label-blind opportunity cohort and its prospective order quantities. Only after that cohort, requests, cost limits, and no-retry rules are published may a separate execution authorization be considered. Primary and stress execution scenarios must use identical opportunities.

## Files

- Contract: `research/strategy/microstructure-behavioral-comparison-v0.1.json`
- Validator and comparator: `src/momentumbot/research/microstructure_behavioral_comparison.py`
- Tests: `tests/test_microstructure_behavioral_comparison.py`
