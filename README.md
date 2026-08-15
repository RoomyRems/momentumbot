# MomentumBot

MomentumBot is a research-first implementation of Ross Cameron's small-cap momentum methodology, built from an evidence-backed corpus of public educational videos and tested as a causal deterministic strategy before any AI judgment is allowed into the decision path.

The near-term release target is **backtesting + paper trading only**.

## Design principles

- **Simple core, explicit states.** Avoid the configuration explosion that makes a strategy impossible to reason about.
- **Evidence-backed rules.** Every strategy rule has a stable ID, evidence references, an era, a confidence level and a deterministic/AI responsibility.
- **No look-ahead leakage.** Historical recaps and videos published after the simulated timestamp cannot influence a replay.
- **AI is advisory.** The planned AI layer scores contextual quality; it never sends broker orders and never overrides hard risk limits.
- **Execution is part of the strategy.** Spread, slippage, liquidity and order impact are measured rather than assumed away.
- **No-trade is valid.** The simulator never forces a position just to create more samples.

## Phase 1: corpus and evidence foundation

The first code in this repository intentionally does not trade. It provides:

- transcript JSONL normalization and validation;
- corpus auditing and topic discovery;
- publication-date/as-of leakage splits;
- a typed evidence/rule schema;
- a bootstrap current-era rulebook;
- unit tests and CI.

See:

- `docs/research/corpus_audit_2026-08-14.md`
- `docs/research/methodology.md`
- `docs/strategy/current_rulebook.md`
- `research/rules/current_rules.json`

## Local corpus audit

Raw transcripts stay outside Git. With local files available:

```bash
python -m pip install -e .
momentumbot-corpus-audit data/raw/daytradewarrior/*.jsonl.txt
```

A leakage-aware split can be inspected with:

```bash
momentumbot-corpus-audit data/raw/daytradewarrior/*.jsonl.txt --as-of 2025-01-01
```

Records whose publication dates are missing are reported as quarantined rather than silently included.

## Planned architecture

```text
market/news data
      |
feature engine + deterministic candidate ranker
      |
setup / momentum-phase state machines
      |
(optional) AI shadow quality review
      |
hard deterministic risk governor
      |
execution simulator / paper broker
      |
campaign journal + replay + ablation reports
```

The raw transcript corpus is **not** in this graph. It exists only in the offline research process that produces versioned rulebooks and labeled examples.

## Next build slice

After Phase 1 is validated, the next code slice will define causal market-data contracts and implement the deterministic candidate/feature model: five pillars, daily-chart room, attention/obviousness, momentum phase, first-pullback detection, session risk state and campaign journaling. Alpaca/FMP/MarketAux credentials are not required for the corpus phase and should remain unused until data adapters are introduced.
