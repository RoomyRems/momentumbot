# Research methodology

MomentumBot is being built as an evidence-backed trading research system, not as a transcript chatbot. The target is a causal deterministic baseline first, followed by an AI shadow reviewer for the residual contextual judgments.

## Evidence classes

Every extracted observation is labeled as a rule, preference, exception, mistake/self-critique, observation, market-regime adaptation, or research guard. Evidence is also labeled normative teaching, observed behavior, self-critique, or research design.

A red-day recap where Ross says he became emotionally compromised is therefore not promoted as recommended behavior; it is negative behavioral evidence supporting a hard risk governor.

## Strategy eras

The corpus spans 2013-2026. Some elements are remarkably stable, especially pullback-based momentum entries and walk-away discipline. Other thresholds evolved. Current full training is stricter about five-times RVOL and low float than some older material. MomentumBot uses named policy eras/profiles instead of turning historical differences into optimizer knobs.

## Leakage controls

```text
simulated timestamp T
        |
        +-- market data available at T
        +-- news published by T
        +-- point-in-time float/universe available at T
        +-- distilled strategy knowledge published/approved for that era
        x-- future candles or final daily volume
        x-- future news
        x-- current float projected backward
        x-- retrospective recap retrieval
        x-- undated transcript evidence
```

## Deterministic versus AI responsibility

Deterministic code owns measurable facts and all safety: gain, RVOL, float, volume, VWAP, EMA9, MACD, pullback geometry, top-gainer rank, spread/slippage when available, order state, sizing, max loss and session lockouts.

The planned AI reviewer receives structured features and may eventually score catalyst substance, theme saturation, ambiguous chart cleanliness and conflicting tape evidence. It cannot submit broker orders and cannot raise risk above deterministic limits.

## Experimental sequence

1. Corpus normalization and chronology guards.
2. Evidence-backed current rulebook.
3. Deterministic candidate/setup/risk baseline.
4. Frozen full-universe market snapshots and causal replay.
5. Component ablations and walk-forward validation.
6. AI shadow reviewer with structured inputs/outputs.
7. Time-safe imitation benchmark against documented behavior.
8. Deterministic versus hybrid backtests on identical data/execution assumptions.
9. Shadow paper trading, then paper execution.
10. Historical Level-2/trade/depth phase only if the simpler system earns it.

No live-money execution is in scope.
