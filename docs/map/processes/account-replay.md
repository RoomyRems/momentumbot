---
type: process
id: process-account-replay
title: "Replay chronological account paths"
cluster: execution-and-risk
universe: live
entity: src/momentumbot/research/sealed_historical_account_replay_v01.py
verified_at: 2026-10-16
verified_commit: 53989a5f1637e759a3922980b40f24cbfbaab5fb
sources: ["src/momentumbot/research/sealed_historical_account_replay_v01.py:51-84", "src/momentumbot/research/sealed_historical_account_replay_v01.py:311-343", "src/momentumbot/research/early_pullback_panel_account_engine_v01.py:347-436", "src/momentumbot/research/early_pullback_panel_account_engine_v01.py:439-493", "src/momentumbot/research/prospective_daily_source.py:778-888", "src/momentumbot/research/sealed_historical_micro_runtime_v01.py:327-353", "src/momentumbot/research/early_pullback_panel_sources_v01.py:305-318"]
status: verified
consumes: ["docs/map/objects/micro-replay.md", "docs/map/objects/execution-account.md"]
produces: ["docs/map/objects/execution-account.md"]
---

# Replay chronological account paths

The account replay consumes source-authenticated opportunities in event order, applies frozen capital/execution rules and carries the resulting state across sessions.

## Input → Movement → Output

Input is the exact registered original-source reader, authenticated Micro **trigger** opportunities, execution sources, frozen path program and mechanically derived initial account state. Sessions simulate execution from those events and reconcile balances, fees, reservations and unresolved positions. Output is hashed runtime/close evidence for every path, including failures or incomplete carry rather than fabricated flat closes.

## Why this shape

Resetting an account each day or accepting caller-supplied balances would erase real dependencies. The historical entry point rejects arbitrary source readers/accounts, verifies the binding manifest and seeds only once; each subsequent session receives the exact prior close (`sealed_historical_account_replay_v01.py:311-343`). Historical provenance alone does not grant financial-metric or live-order authority.

The Micro edge means `MicroTriggerDecision` from `prospective_daily_source.py:778-888`, frozen without fill/account simulation by the historical wrapper (`sealed_historical_micro_runtime_v01.py:327-353`) or authenticated in the synthetic new-panel binder (`early_pullback_panel_sources_v01.py:305-318`). The separate diagnostic `MicroCandidateReplay` and its simulated fills do **not** feed this modern account route.

## Steps

1. Verify the frozen registration and require the exact original-source reader and manifest (`sealed_historical_account_replay_v01.py:311-322`).
2. Build frozen programs, initialize each account once and iterate all registered sessions with high-precision arithmetic (`:323-334`).
3. Apply chronological scheduler and execution mechanics. The new-panel bridge demonstrates original source checks, stable rank, capacity/lock gates and an explicit selection-only withholding branch (`early_pullback_panel_account_engine_v01.py:347-436`).
4. Preserve positions, pending orders, gaps, failures and exact fees when producing close state; the new-panel finisher remains explicitly synthetic (`:439-493`).
5. Seal path completeness and final close identity without opening retrospective labels (`sealed_historical_account_replay_v01.py:335-343,51-84`).

## If you change this

- **Hits:** Capital competition, allowed entries, fee totals, account locks, carry continuity and every later state on affected paths.
- **Does not hit:** Causal scanner thresholds or label interpretation; no external brokerage order is authorized. Synthetic new-panel evidence does not become historical evidence through shared mechanics.

## Surfaces

| Surface | Role |
|---|---|
| Authenticated original reader | Supplies committed source streams |
| Session scheduler/engine | Moves state deterministically |
| Runtime and close envelopes | Preserve reconciliation and failure evidence |
| Downstream evaluator | Reads frozen results, never supplies opening state |

## See

- Objects: [Micro replay](../objects/micro-replay.md), [execution/accounts](../objects/execution-account.md)
- [Historical owner](../../../src/momentumbot/research/sealed_historical_account_replay_v01.py)
- [New-panel bridge](../../../src/momentumbot/research/early_pullback_panel_account_engine_v01.py)
- [Trigger producer](../../../src/momentumbot/research/prospective_daily_source.py)
- [Historical trigger wrapper](../../../src/momentumbot/research/sealed_historical_micro_runtime_v01.py)
- [Synthetic trigger binder](../../../src/momentumbot/research/early_pullback_panel_sources_v01.py)
