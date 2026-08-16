# Deterministic Micro v0.1 — frozen research baseline

Status: **frozen for generalization research**.

Micro v0.1 is the first named deterministic sub-minute baseline. Its purpose is not to claim that every machine translation below is optimal or directly authored by Ross Cameron. Its purpose is to stop the research process from silently changing the strategy while the benchmark suite and walk-forward dataset are expanded.

The executable contract lives in `src/momentumbot/micro_policy.py`. Every result that claims to use Micro v0.1 should record that policy's fingerprint.

## Frozen setup contract

- Setup family: canonical chart-confirmed micro pullback.
- Micro chart interval: 10 seconds.
- Candidate prerequisite: the stock must already have qualified through the causal market-selection layer. Micro v0.1 does not redefine stock selection.
- Fast impulse followed by a one-or-more-candle micro pullback/pause.
- Pullback duration translation: at most 5 completed 10-second bars.
- Impulse-base translation: minimum low across the 5-bar impulse lookback ending at the strict running-high peak.
- Equal-high retests do not create a new peak; only a strict new running high can re-anchor the pullback.
- Maximum retracement: 50% of the translated impulse range.
- Pullback mean volume must be lower than impulse mean volume.
- Peak upper-wick fraction must be below 50%.
- Pullback low must remain at/above causal session VWAP.
- Pullback low must remain at/above causal EMA9. EMA9 may use prior-bar warmup; VWAP resets with the current session.
- Slower-chart support values become available only after the relevant one-minute candle has completed.
- Entry trigger: while the next 10-second candle is forming, price must make a new high over the immediately preceding completed pullback candle. With the current $0.01 tick translation, the minimum trigger price is previous-candle high + $0.01.
- Initial chart invalidation / stop reference: pullback low.

## Deliberately excluded from Micro v0.1

These are not silently selectable options inside the baseline:

- half-dollar or whole-dollar continuation triggers;
- hidden-buyer / Level-2 anticipation;
- tape-based anticipatory entry;
- odd-lot transaction triggering of the chart breakout;
- advanced high-of-day breakout variants;
- AI approval/rejection;
- benchmark-specific latency or slippage calibration;
- a fitted fixed profit target;
- automatic optimization of the 5-bar impulse lookback or 5-bar maximum pullback duration.

They may be evaluated later as separately named ablations or advanced policies.

## Evidence versus machine translation

The source corpus supports the 10-second micro concept, controlled pullback, roughly <=50% retracement, lighter selling, VWAP/EMA support, first-candle-new-high entry, pullback-low risk reference, and rapid expected resolution. The exact five-bar impulse lookback and five-bar maximum pullback duration are machine translations because the corpus does not uniquely specify them. Freezing them now is an experimental-control decision, not a claim that they are sacred strategy constants.

## Change control

`micro-v0.1` is immutable. If later evidence or out-of-sample results justify changing a frozen field, create a new named policy version (for example `micro-v0.2`) and compare it against v0.1 on the same frozen data. Do not edit v0.1 in place.

Research-only helpers such as geometry-only evaluation and psychological-level continuation remain available, but a result using them must not be labeled Micro v0.1.

## Promotion criterion

Freezing does **not** mean production-ready. Micro v0.1 remains a research baseline until it has been evaluated across multiple leakage-safe labeled examples and broader walk-forward historical days. No live-money execution is in scope.
