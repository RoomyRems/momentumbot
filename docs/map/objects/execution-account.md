---
type: object
id: object-execution-account
title: "Execution and account state"
cluster: execution-and-risk
universe: live
status: verified
entity: src/momentumbot/research/sealed_historical_account_replay_v01.py
verified_at: 2026-10-16
verified_commit: 53989a5f1637e759a3922980b40f24cbfbaab5fb
sources: ["src/momentumbot/research/sealed_historical_account_replay_v01.py:1-30", "src/momentumbot/research/sealed_historical_account_replay_v01.py:51-84", "src/momentumbot/research/sealed_historical_account_replay_v01.py:311-343", "src/momentumbot/research/early_pullback_panel_account_engine_v01.py:1-38", "src/momentumbot/research/early_pullback_panel_account_engine_v01.py:347-436", "src/momentumbot/research/early_pullback_panel_account_engine_v01.py:439-493", "src/momentumbot/research/prospective_daily_source.py:778-888", "src/momentumbot/research/sealed_historical_micro_runtime_v01.py:327-353", "src/momentumbot/research/early_pullback_panel_sources_v01.py:305-318"]
---

# Execution and account state

The sealed account family turns source-bound opportunities into chronological simulated account state with explicit fees, reservations, failures and carry.

## Why this shape

Independent candidate fills cannot establish portfolio performance: candidates compete for finite capital and an unresolved position affects later sessions. The historical entry point accepts only authenticated original sources, seeds once per path and carries the exact previous close forward (`sealed_historical_account_replay_v01.py:311-343`). It cannot accept caller-invented accounts or rescue an unavailable entry with invented prices.

## Shape

The historical replay's boundaries distinguish authenticated historical execution from financial-metric eligibility and deny broker orders and promotion (`:51-84`). Its continuity, scheduler, fees and producer imports remain active ancestors. The newer early-pullback bridge preserves those mechanics by isolated subclasses/context substitutions, with AST-equivalence tests described in its module contract (`early_pullback_panel_account_engine_v01.py:1-38`).

The bridge orders opportunities, registers bars/trade cursors and checks capacity, account lock and entry blocks before submission (`:347-436`). Its finisher preserves unresolved inputs, positions and pending orders; equity may remain unavailable until flat. That bridge's envelope is explicitly synthetic (`:439-493`), not a completed real-source new-panel backtest.

Its Micro input is authenticated `MicroTriggerDecision` evidence emitted without fills by `prospective_daily_source.py:778-888`, frozen historically at `sealed_historical_micro_runtime_v01.py:327-353` or rebuilt by the synthetic binder at `early_pullback_panel_sources_v01.py:305-318`. It is **not** the diagnostic `MicroCandidateReplay` plan/fill artifact; account execution is simulated here from bound triggers and execution sources.

## Connected to

- **owns:** Account state transitions, finite-capital scheduling and session-close evidence.
- **owned-by:** Frozen mechanics and authenticated source bindings.
- **joins:** The [Micro trigger branch](micro-replay.md) supplies authenticated trigger evidence, not diagnostic fills; [research/evaluation](research-evaluation.md) reads completed or explicitly incomplete account results.
- **looks-like-but-is-not:** A broker API, a per-candidate fill report, or the legacy CLI baseline.

## If you change this

- **Hits:** Allocation order, sizing, reservations, fees, realized balances, unresolved carry and all subsequent sessions on a path.
- **Does not hit:** Scanner eligibility or retrospective labels; no change here grants live-order, overnight-execution or policy-promotion authority.

## Surfaces

| Surface | Role |
|---|---|
| Historical public replay entry | Consumes exact authenticated original sources |
| Scheduler and engine ancestors | Apply deterministic mechanics and reconciliation |
| New-panel context bridge | Exercises preserved mechanics in synthetic scope |
| External runtime consumers | Unknown; historical output paths remain fixed |

## See

- [Historical replay owner](../../../src/momentumbot/research/sealed_historical_account_replay_v01.py)
- [New-panel bridge](../../../src/momentumbot/research/early_pullback_panel_account_engine_v01.py)
- [Trigger producer](../../../src/momentumbot/research/prospective_daily_source.py)
- [Historical trigger wrapper](../../../src/momentumbot/research/sealed_historical_micro_runtime_v01.py)
- [Synthetic trigger binder](../../../src/momentumbot/research/early_pullback_panel_sources_v01.py)
- [Account replay movement](../processes/account-replay.md)
