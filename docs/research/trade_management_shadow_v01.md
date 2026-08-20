# Trade-management shadow v0.1

## What changed

This experiment adds a causal chart-only management layer **after** each already-frozen Micro-v0.1 fill. It does not change scanner selection, entry detection, entry fills, original stops, account qualification, accepted quantities or the prospective August 24–September 4 account study.

The source evidence distinguishes a pre-entry 2:1 opportunity test from a mandatory full-position target. Current training permits taking half at the first target, moving the remainder to breakeven, and holding that remainder for a valid exit indicator. It also teaches red candles, topping tails, displayed or hidden sellers, red tape, false breakouts and slowing buying as adverse evidence. Only the parts supported by the frozen market data and an exact machine rule are active here.

The four cells were registered in `research/strategy/trade-management-shadow-v0.1.json` before any July management path was executed:

| Cell | First target | Chart exit |
| --- | --- | --- |
| `full-first-red-10s` | No scale-out | Full exit after first completed red 10-second candle |
| `half-2r-breakeven-first-red-10s` | Sell half at 2R; remainder stop to actual fill | Exit remainder after first completed red 10-second candle or active stop |
| `full-first-red-1m` | No scale-out | Full exit after first completed red one-minute candle |
| `half-2r-breakeven-first-red-1m` | Sell half at 2R; remainder stop to actual fill | Exit remainder after first completed red one-minute candle or active stop |

Every red-candle decision becomes available only after its bar closes. The next eligible SIP print is the exit proxy. The original stop has priority and can never be widened. A 2R target uses the actual frozen fill and original stop. No end-of-window liquidation is invented.

## Why four cells remain

The evidence does not uniquely resolve whether every micro entry should be managed on its 10-second chart or on the one-minute chart, and half-at-target is permitted rather than universal. Both choices were therefore crossed and reported equally. The July result cannot select a winner.

Level 2 resistance, hidden sellers, aggressor-side red tape, buying-rate slowdown, numeric large-topping-tail and high-volume-red-candle thresholds, later scale targets and cushion-dependent hold-through behavior are deferred. The frozen SIP trades do not contain displayed depth or a trustworthy aggressor side.

## Frozen result

The exact result is `research/frozen/trade-management-shadow-v0.1/manifest.json`, content SHA-256 `b06159fee47d1d0f59a8d67aabfc082a1c3af6872a88f18f9a7eb49a3f969434`. Two independent builds were byte-identical; the file SHA-256 is `400623d1022daed8c21548d063212258de6e794f733a0847b0f494077f76782b`.

All 87 already-filled Micro plan outcomes closed under every cell. These outcomes overlap heavily and therefore do not form a strategy trade sequence.

| Cell | Target touches | Exit mix | Sum weighted realized R |
| --- | ---: | --- | ---: |
| Full / 10s | 19 | 32 initial stops, 55 red candles | -23.2916R |
| Half / 10s | 19 | 29 initial stops, 19 targets, 8 breakeven stops, 50 red candles | -14.0833R |
| Full / 1m | 22 | 56 initial stops, 31 red candles | -21.4981R |
| Half / 1m | 22 | 50 initial stops, 22 targets, 13 breakeven stops, 24 red candles | -26.5540R |

The R sums are engineering diagnostics over overlapping plans, not expectancy.

The fixed-entry account overlay applies each path only to entries accepted by the prior account diagnostic. It does not recycle earlier exit capital or admit previously rejected entries.

| Account | Full / 10s | Half / 10s | Full / 1m | Half / 1m |
| --- | ---: | ---: | ---: | ---: |
| Main, 10 fixed entries | -$200.70 | -$172.89 | -$441.20 | -$276.89 |
| Small, 2 fixed entries | +$7.20 | +$7.39 | +$5.93 | +$6.88 |

For context, the earlier stop-only fixed-entry diagnostic realized -$680.57 for main, -$5.33 for small and left GMM unresolved. The new chart layer closes GMM favorably and reduces the main loss in every cell, but the main fixed-entry sample remains negative in every cell. The small result is based on only two entries and is driven by the GMM winner. None of these values is a compounded return, economic performance estimate or promotion result.

## Decision

Retain all four cells as shadow evidence. Do not select the least-negative July cell. The result proves that deterministic favorable management can be reconstructed causally from the available bars and prints; it does not prove that the current entry model matches Ross Cameron or has positive expectancy.

The next honest backtest gate is to integrate a **preselected** management rule into chronological account state on genuinely prospective sessions, with realistic spread, latency, partial-fill and cancellation behavior. Level 2 and tape-discretion components require their own data contract. Micro-v0.1 and the August account panel remain unchanged until that gate is registered.

## Reproduction

```bash
PYTHONPATH=src python scripts/build_trade_management_sensitivity.py \
  --micro-zip /path/to/discretion-heldout-micro-runtime-v0.1.zip \
  --output /tmp/trade-management-shadow-v0.1
```

The source/evidence boundary, failed build attempts, exact hashes and result disposition are preserved in `research/data-audits/trade-management-shadow-v0.1-2026-08-19.json`.
