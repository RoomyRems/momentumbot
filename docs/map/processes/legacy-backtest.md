---
type: process
id: process-legacy-backtest
title: "Run the public CLI deterministic baseline"
cluster: legacy-baseline
universe: leftover
entity: src/momentumbot/cli.py
verified_at: 2026-10-16
verified_commit: 53989a5f1637e759a3922980b40f24cbfbaab5fb
sources: ["src/momentumbot/cli.py:11-82", "src/momentumbot/backtest.py:56-121", "src/momentumbot/backtest.py:123-177", "src/momentumbot/backtest.py:188-225"]
status: verified
consumes: []
produces: []
unmapped_io: "Legacy snapshot inputs and BacktestResult are outside the mapped modern object set."
---

# Run the public CLI deterministic baseline

`momentumbot backtest` loads a frozen snapshot and runs the older one-minute `Backtester`, a retained callable baseline distinct from the Micro/sealed-account research path.

## Input → Movement → Output

Input is a snapshot directory with manifest, contexts, bars and news, plus a profile/equity selection. The CLI loads and validates that snapshot, builds the chosen deterministic profile with paper-safe risk and calls `Backtester.run_day`. Output is a JSON summary of simulated trades, events, lock state, P&L and stated universe/promotion scope.

## Why this shape

This simple public entry point remains useful for the deterministic baseline, but its familiar name must not be mistaken for the full hybrid or newer replay engine. `universe: leftover` means outside the active mapped research route, not dead code or deletion permission. The object-edge arrays are empty deliberately: it does not consume the exact-RVOL capture object or produce the sealed-account object described elsewhere.

## Steps

1. Parse the snapshot/profile/equity arguments; conditional current-asset-master scope requires an explicit flag (`cli.py:11-33`).
2. Load the snapshot, choose general/small-account profile and call the baseline with paper-safe risk (`:36-53`).
3. Validate symbol populations and aware bars, then maintain pending plans, positions and session risk state (`backtest.py:84-121`).
4. Process stop/forced exits, next-bar triggers, slippage and whole-share sizing; rank candidates and evaluate first-pullback plans (`:123-177,188-225`).
5. Print results with explicit point-in-time versus conditional-universe scope and the manifest's promotion eligibility (`cli.py:54-82`).

## If you change this

- **Hits:** Public CLI behavior, frozen-snapshot loading, baseline simulated fills and summary output; changes to shared scanner/risk helpers can affect other callers.
- **Does not hit:** The Micro replay or sealed account engine merely because both are called backtests. This path grants no broker-order authority and does not activate context discretion.

## Surfaces

| Surface | Role |
|---|---|
| Public CLI | Reads snapshot/options; prints JSON |
| Baseline Backtester | Simulates one-minute deterministic mechanics |
| Shared scanner/setup/risk helpers | Read by this baseline; inspect other callers before changes |
| External CLI consumers | Unknown; preserve command/format compatibility |

## See

- Distinct objects: [Micro replay](../objects/micro-replay.md), [execution/accounts](../objects/execution-account.md)
- [CLI owner](../../../src/momentumbot/cli.py)
- [Baseline engine](../../../src/momentumbot/backtest.py)
