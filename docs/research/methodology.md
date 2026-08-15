# Research methodology

MomentumBot is being built as an evidence-backed trading research system, not as a transcript chatbot. The goal is to reproduce and test the described methodology while preventing retrospective information from contaminating backtests.

## Evidence classes

Every extracted observation is labeled as one of:

- **Rule:** explicitly taught as a repeatable requirement or guardrail.
- **Preference:** repeatedly favored but not absolute.
- **Exception:** a stated or observed deviation from a normal rule.
- **Mistake / self-critique:** behavior Ross says should not have been taken or managed that way.
- **Observation:** descriptive market behavior without a prescriptive rule.
- **Market-regime adaptation:** behavior that intentionally changes with hot/cold conditions.
- **Research guard:** a MomentumBot integrity requirement such as preventing look-ahead leakage.

Evidence also records whether it is **normative teaching**, **observed behavior**, **self-critique**, or **research design**. This prevents a failed emotional trade from being mined as if it were a recommended setup.

## Strategy eras

The current corpus spans more than a decade. Thresholds and emphasis have changed: examples include relative-volume thresholds, float preferences, position size and the degree of discretionary tape reading. MomentumBot will therefore maintain versioned eras rather than exposing dozens of knobs that can be optimized until a backtest looks good.

The first implementation target is the **current-era baseline**, primarily supported by 2025-2026 material. Older eras remain research subjects for ablation and strategy-evolution work.

## Leakage controls

Historical replay is governed by publication time:

```text
simulated timestamp T
        |
        +-- market data available at T
        +-- news available at T
        +-- strategy knowledge published on/before T
        x-- any transcript/video published after T
        x-- raw retrospective recap retrieval
        x-- records whose publication date is unknown
```

Raw transcript retrieval is never part of the live or paper-trading decision path. The agent receives only a versioned, structured strategy specification and the market state available at the decision timestamp.

## Deterministic versus AI responsibilities

Use deterministic code whenever the state can be measured reliably: price, percent change, RVOL, float, daily levels, VWAP/EMA/MACD state, pullback depth, volume profile, spread, slippage, risk budgets, session lockouts and order state.

The initial shadow AI layer is reserved for contextual judgments that remain hard to encode without losing meaning: catalyst substance, theme saturation/novelty, ambiguous chart cleanliness and conflicting Level-2/tape evidence. AI has **no broker permission** and cannot override hard risk limits.

## Experimental sequence

1. Validate and normalize the corpus.
2. Build the evidence-backed current rulebook.
3. Implement a deterministic baseline with causal features only.
4. Run component ablations before adding AI.
5. Add an AI shadow reviewer with structured inputs/outputs.
6. Build an imitation benchmark against time-safe examples.
7. Compare deterministic vs hybrid variants on identical market data and execution assumptions.
8. Shadow paper trade, then paper execute only after the simulator is trusted.
9. Add historical Level-2/depth data as a later, more expensive phase.

No live-money execution is in scope for the initial releases.
