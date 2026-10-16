---
type: object
id: object-micro-replay
title: "Micro triggers and diagnostic replay"
cluster: setup-and-replay
universe: live
status: verified
entity: src/momentumbot/research/prospective_daily_source.py
verified_at: 2026-10-16
verified_commit: 53989a5f1637e759a3922980b40f24cbfbaab5fb
sources: ["src/momentumbot/research/prospective_daily_source.py:73-78", "src/momentumbot/research/prospective_daily_source.py:158-176", "src/momentumbot/research/prospective_daily_source.py:778-888", "src/momentumbot/research/sealed_historical_micro_runtime_v01.py:327-353", "src/momentumbot/research/early_pullback_panel_sources_v01.py:305-318", "src/momentumbot/micro_replay.py:103-198", "src/momentumbot/micro_replay.py:227-248"]
---

# Micro triggers and diagnostic replay

The Micro family has two distinct outputs: account-neutral `MicroTriggerDecision` records and separate `MicroCandidateReplay` diagnostic plan/fill records. They are not interchangeable.

## Why this shape

Trigger production must not pre-decide account execution. The primary producer emits only the first qualifying price crossing for each causal plan, with its evidence hash; no fill or later outcome enters that decision (`prospective_daily_source.py:778-888`). Diagnostic replay separately simulates armed plans to study setup/execution behavior (`micro_replay.py:114-198`).

## Shape

`ProfileActivation` binds qualification to scanner evidence and eligible profiles. `MicroTriggerDecision` binds activation, plan, decision time and causal-prefix hash (`prospective_daily_source.py:158-176`). The producer reuses `causal_active_pullback_number` from `micro_replay.py`, not its diagnostic replay output (`:73-78,778-888`).

The sealed historical wrapper freezes these trigger records with `fills_simulated=False` and `accounts_simulated=False` (`sealed_historical_micro_runtime_v01.py:327-353`). The synthetic new-panel binder rebuilds/authenticates the same trigger path (`early_pullback_panel_sources_v01.py:305-318`). Separately, `micro_replay_runtime_artifact` serializes diagnostic plan/outcome steps for post-replay comparison (`micro_replay.py:227-248`). “Live” here means exercised research code, never live-money authority.

## Connected to

- **owns:** Causal trigger records; a separate diagnostic replay family also records simulated outcomes.
- **owned-by:** Qualified [scanner](causal-scanner.md) activations and frozen Micro policies.
- **joins:** [Execution/accounts](execution-account.md) consume authenticated **trigger** evidence. [Micro comparison](research-evaluation.md) can consume the separately frozen diagnostic artifact.
- **looks-like-but-is-not:** A trigger is not a fill; diagnostic fills are not modern sealed/new-panel account inputs.

## If you change this

- **Hits:** Shared setup/ordinal changes affect both branches. Trigger-producer changes affect account opportunity evidence; diagnostic-simulator changes affect diagnostic outcomes only unless a shared dependency changes.
- **Does not hit:** Editing diagnostic serialization alone does not change modern account triggers. Neither branch owns provider scope, account seed/carry rules or broker connectivity.

## Surfaces

| Surface | Role |
|---|---|
| Trigger producer | Writes account-neutral causal crossing decisions |
| Historical/synthetic binders | Preserve/authenticate trigger evidence without fills |
| Diagnostic replay/simulator | Writes separate plan/outcome evidence |
| Modern account engine | Consumes bound triggers and simulates execution itself |

## See

- [Primary trigger owner](../../../src/momentumbot/research/prospective_daily_source.py)
- [Historical trigger wrapper](../../../src/momentumbot/research/sealed_historical_micro_runtime_v01.py)
- [Synthetic trigger binder](../../../src/momentumbot/research/early_pullback_panel_sources_v01.py)
- [Separate diagnostic replay](../../../src/momentumbot/micro_replay.py)
- [Micro replay movement](../processes/micro-replay.md)
