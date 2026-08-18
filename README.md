# MomentumBot

MomentumBot is a research-first implementation of Ross Cameron's small-cap momentum methodology, derived from a metadata-enriched corpus of 2,292 public educational/recap videos and tested as a causal deterministic strategy before any AI judgment is allowed into the decision path.

**Current scope: deterministic research + backtesting foundation. No live-money trading.**

For a cold-start project map, current checkpoint and experiment protocol, begin with `AGENTS.md` and `docs/project/current_state.md` rather than loading the full repository.

## What is implemented

- transcript normalization, chronology splits and leakage guards;
- a machine-validated evidence registry with current-era rules;
- named general and small-account strategy profiles;
- five-pillars candidate assessment with explicit A-quality vs conditional status;
- top-gainer/attention ranking without fitted score weights;
- VWAP, EMA9 and standard 12/26/9 MACD;
- first-pullback confirmation plan with <=50% retrace and contracting volume;
- first-candle-new-high trigger, pullback-low stop and >=2R room to prior high;
- fill/slippage revalidation before accepting an entry;
- uncapped chart-based winners with red-candle/topping-tail baseline exits;
- deterministic session risk state and irreversible lockouts;
- frozen-snapshot contract requiring a complete universe and point-in-time float;
- conservative OHLC ambiguity handling;
- campaign IDs so repeated entries in one ticker episode are not mistaken for independent ideas.

## Evidence discipline

Raw transcripts are never runtime strategy context. They stay offline and are used to create versioned distilled rulebooks. Historical replay cannot retrieve a recap published after the date being simulated, and undated transcripts are quarantined from chronology-sensitive experiments.

See `docs/research/methodology.md`, `docs/research/strategy_evolution.md`, and `docs/strategy/current_rulebook.md`.

## Install and test

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

## Corpus audit

```bash
momentumbot-corpus-audit data/raw/daytradewarrior/*.jsonl.txt --as-of 2025-01-01
```

## Frozen snapshot backtest

```bash
momentumbot backtest path/to/snapshot --profile general-2026
```

The simulator uses the separate `paper-safe` risk policy by default. The aggressive percentages discussed in small-account challenge videos are research subjects, not the project's paper safety defaults.

## Current gate

The ten-session scanner, unchanged Micro-v0.1 replay, retrospective Ross labels and no-retuning component comparison are frozen. Context-assessment protocol v0.1 is now also preregistered: it requires hashed decision-time evidence, citations, explicit fact/inference separation, abstention, bounded expiry and no order or risk authority. The active gate is a new label-blind held-out context panel, not fitting the reviewed pilot. See `docs/project/current_state.md` for the exact checkpoint and next steps.

The provisional universe makes an auditable decision for every fetched historical ticker but remains explicitly non-promotable until those downstream gates are complete. A current provider asset census—even one containing inactive rows—remains conditional diagnostic evidence only. AI remains shadow-only until the deterministic baseline has credible walk-forward results.
