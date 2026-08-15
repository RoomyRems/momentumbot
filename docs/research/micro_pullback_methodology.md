# Micro-pullback research methodology

This document records the current evidence boundary for MomentumBot's sub-minute strategy research. It deliberately separates what Ross Cameron teaches as the ordinary chart-confirmed micro pullback from experienced discretionary exceptions that depend on Level 2, time-and-sales, psychological levels, or other context.

## Why a separate micro layer exists

The one-minute deterministic control remains intentionally strict. The transcript corpus repeatedly describes fast momentum names that never provide a proper one-minute pullback; the April 22, 2026 dedicated micro-pullback class explicitly uses a 10-second chart for those cases. The July 9 VRAX reconstruction independently demonstrates the data-resolution problem: the reported second micro pullback, break through $6, surge and rejection are compressed inside one consolidated one-minute candle.

Therefore MomentumBot does **not** relax the one-minute pullback rules to manufacture fast trades. It keeps the one-minute baseline as a control and adds a separate micro-timeframe research layer.

## Evidence-backed canonical chart setup

Current evidence supports this ordinary sequence:

1. The stock has already passed the market/stock-selection layer and is experiencing exceptional rate of change and volume.
2. A fast impulse occurs.
3. Price pauses or pulls back for one or more fast-timeframe candles. In the simple beginner formulation this may be one candle; the dedicated April class shows multi-candle 10-second pullbacks as well.
4. The pullback should generally not retrace more than about 50% of the initial impulse.
5. The chart-confirmed trigger is the first fast-timeframe candle to make a new high over the preceding candle. Entry occurs while that candle is forming, not after it closes.
6. The pullback low is the logical chart invalidation / maximum-loss reference.
7. Resolution is expected quickly. The April class describes the trade as "breakout or bailout": failure to resolve as expected is itself adverse information.
8. Initial reward must have enough room to justify the risk. For micro continuation trades the transcript corpus often discusses a retest of the prior high followed by the next half/whole-dollar area and broader daily-chart room; this should not be reduced to an unconditional fixed profit target.

The exact machine definition of the impulse origin for the 50% test is **not uniquely specified in the source material**. That translation must remain explicit and be evaluated against multiple labeled examples rather than optimized silently.

## What is not part of the canonical chart-only baseline

### Hidden-buyer / Level-2 anticipation

Ross explicitly describes anticipating the usual first-new-high trigger when Level 2 and time-and-sales reveal an unusually clear buyer/support condition. The April 22 AGPU case is an example: the narration attributes the decision to punch the trade around the $8 area to stacked bid support and green prints.

MomentumBot will not approximate that by simply lowering the deterministic trigger. It belongs in a later market-microstructure/context layer.

### Whole-dollar / half-dollar anticipation

Half and whole dollars recur as psychological support, resistance and continuation targets. They are useful deterministic context features, but a round number by itself is not an entry signal. An anticipatory entry at such a level remains a separate advanced policy until the required order-flow context is available.

### Advanced high-of-day continuation / breakout entries

Some recaps describe entries explicitly "for the break of" a high or a round-number level after a micro consolidation. These can overlap with the micro-pullback family but are not automatically equivalent to the ordinary chart-confirmed first-new-high setup. They should be labeled and tested as a separate setup family if the corpus continues to support that distinction.

## Historical data contract

The micro research layer uses historical consolidated SIP trade prints. Derived 10-second bars apply Alpaca's published minute-bar trade-condition eligibility so prints that are not allowed to update OHLC do not silently create false highs/lows. Unknown condition codes fail closed.

For validated reference windows, the same trade-print aggregation reproduces Alpaca's official complete one-minute OHLCV bars exactly. The derived 10-second bars are nevertheless labeled as research-derived bars rather than exchange/provider-published candles.

Expensive trade-print data is fetched only after the cheaper market-selection layer has identified a candidate and only for the necessary time window. MomentumBot will not download tick data for the entire U.S. market.

## Labeled benchmarks

### VRAX — 2026-07-09

Use: advanced continuation, pullback ordinal and execution/slippage benchmark.

The same-day recap says Ross skipped the first pullback, took the second micro pullback for the break of $6, and was filled around $6.30 as the stock accelerated. Historical SIP prints independently show the first eligible $6 print and a $6.30+ print less than five seconds apart. Candidate-anchored 10-second observations also show two confirmed pullbacks after the stock first qualified.

This is **not** the preferred benchmark for defining the ordinary chart-only trigger because the reported entry is framed around a specific breakout level and execution behavior.

### AGPU — 2026-04-22

Use: Level-2 anticipation and support-context benchmark.

The dedicated class reports a move to roughly $8.50, a dip around/below $8, entries around $8.33/$8.50, and a stop just below $8. Historical SIP data independently reconstructs the $8.50 print, a drop to $7.78, and the recross through $8.50 within seconds. The narration explicitly cites stacked buyers at $8 plus green time-and-sales prints as the reason to punch the trade, so this is an excellent benchmark for the future order-flow/context layer rather than a pure chart-only calibration target.

### DSY — 2026-06-10

Use: candidate chart-only canonical micro benchmark under construction.

The recap describes a 10-second micro pullback with fills around $3.07/$3.11 and restates the normal crossing-candle / first-candle-new-high entry logic without attaching a hidden-buyer justification to that first trade. Historical SIP reconstruction is used to determine whether the chart-only causal model reproduces this behavior without special price rules.

## Evaluation discipline

A retrospective benchmark file is ground truth only. It is never supplied to the strategy while replaying that historical moment. The policy receives only data that was actually available by the simulated timestamp. Benchmark labels are scored after the replay.

A deterministic micro rule must work across multiple labeled examples before it can be promoted into the baseline. If a rule is required only to reproduce one famous trade, it remains an ablation or an advanced-context hypothesis rather than a production default.
