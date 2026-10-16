---
type: process
id: process-micro-replay
title: "Produce causal Micro triggers"
cluster: setup-and-replay
universe: live
entity: src/momentumbot/research/prospective_daily_source.py
verified_at: 2026-10-16
verified_commit: 53989a5f1637e759a3922980b40f24cbfbaab5fb
sources: ["src/momentumbot/research/prospective_daily_source.py:73-78", "src/momentumbot/research/prospective_daily_source.py:158-176", "src/momentumbot/research/prospective_daily_source.py:778-888", "src/momentumbot/research/sealed_historical_micro_runtime_v01.py:327-353", "src/momentumbot/research/early_pullback_panel_sources_v01.py:305-318", "src/momentumbot/micro_replay.py:114-198", "src/momentumbot/micro_replay.py:227-248"]
status: verified
consumes: ["docs/map/objects/causal-scanner.md"]
produces: ["docs/map/objects/micro-replay.md"]
---

# Produce causal Micro triggers

The modern account-source movement emits causal `MicroTriggerDecision` records without simulating fills; diagnostic replay is a separate sibling path.

## Input → Movement → Output

Input is a scanner-derived `ProfileActivation`, Micro bars, trades, support and entry cutoff. The trigger producer evaluates causal prefixes and finds each plan's first eligible chart-price crossing. Output is an ordered trigger list bound to activation, plan and causal-prefix hashes—not a fill list or account ledger.

## Why this shape

Setup qualification and trigger occurrence must remain independent of finite-capital execution. Choosing favorable fills before account replay would import later outcomes into its opportunity set. The producer explicitly emits no fill/later outcome (`prospective_daily_source.py:778-786`), and the historical wrapper preserves that boundary (`sealed_historical_micro_runtime_v01.py:327-353`).

## Steps

1. Validate the frozen Micro policy, aware timestamps, bars/trades/support and pre-cutoff activation (`prospective_daily_source.py:778-806`).
2. Evaluate each completed action prefix using the shared causal pullback-ordinal helper; retain plans with an eligible price crossing inside their armed/expiry window (`:807-834`).
3. Bind the plan and available bars/support/trades to a causal-prefix hash, then emit ordered, unique trigger decisions (`:835-888`).
4. Freeze historical trigger records with no fill/account simulation (`sealed_historical_micro_runtime_v01.py:327-353`); the synthetic new-panel route separately rebuilds and authenticates these same decisions (`early_pullback_panel_sources_v01.py:305-318`).

**Separate diagnostic fork:** `replay_micro_candidate` evaluates plans and calls `simulate_micro_entries`, producing `MicroCandidateReplay`; its serializer permits later benchmark comparison (`micro_replay.py:114-198,227-248`). This diagnostic artifact is not the modern account-source output. The two branches share setup/ordinal helpers, not their final records.

## If you change this

- **Hits:** Trigger timing, source evidence hashes and account opportunity populations. Shared setup/ordinal changes also affect the separate diagnostic branch.
- **Does not hit:** Trigger production does not determine fills, fees, sizing or capital competition. A diagnostic-only serialization change does not change this trigger stream; neither path submits broker orders.

## Surfaces

| Surface | Role |
|---|---|
| Trigger builder | Reads causal prefixes; emits crossing decisions |
| Historical/synthetic binders | Preserve or authenticate trigger evidence |
| Modern account engine | Simulates execution from bound triggers |
| Separate diagnostic replay | Produces plan/fill records for diagnostic comparison |

## See

- Objects: [Causal scanner](../objects/causal-scanner.md), [Micro replay](../objects/micro-replay.md)
- [Trigger owner](../../../src/momentumbot/research/prospective_daily_source.py)
- [Historical trigger wrapper](../../../src/momentumbot/research/sealed_historical_micro_runtime_v01.py)
- [Separate diagnostic replay](../../../src/momentumbot/micro_replay.py)
- [Synthetic source bridge](../../../src/momentumbot/research/early_pullback_panel_sources_v01.py)
