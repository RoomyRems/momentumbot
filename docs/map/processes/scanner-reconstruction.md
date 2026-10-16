---
type: process
id: process-scanner-reconstruction
title: "Reconstruct causal scanner dispositions"
cluster: candidate-discovery
universe: live
entity: src/momentumbot/causal_scanner_snapshot_v03.py
verified_at: 2026-10-16
verified_commit: 53989a5f1637e759a3922980b40f24cbfbaab5fb
sources: ["src/momentumbot/causal_scanner_snapshot_v03.py:183-229", "src/momentumbot/causal_scanner_snapshot_v03.py:350-454", "src/momentumbot/research/early_pullback_panel_sources_v01.py:202-235", "src/momentumbot/research/early_pullback_panel_sources_v01.py:263-326", "src/momentumbot/research/candidate_rvol_exact.py:87-89"]
status: verified
consumes: ["docs/map/objects/causal-scanner.md"]
produces: ["docs/map/objects/causal-scanner.md"]
---

# Reconstruct causal scanner dispositions

The v0.3 builder converts supplied canonical source inputs into ordered candidate-minute decisions with a fixed raw/split adjustment basis.

## Input → Movement → Output

Input is a complete resolved membership plus candidate frames, previous closes, exact-RVOL series, float and timestamped news evidence. The builder validates input basis, delegates shared causal mechanics and independently checks split-consistent market semantics. Output is a canonical disposition tape and hashed manifest, not evidence of a complete market universe.

## Why this shape

Raw displayed prices and split-adjusted gain/rank serve different purposes. Silently treating their numerical values as interchangeable would change eligibility or ranking around corporate actions. Source fingerprints and explicit completeness flags make the limited scope visible to consumers.

## Steps

1. Supply the typed source populations and validate membership/raw/split basis before computing rows (`causal_scanner_snapshot_v03.py:183-205`).
2. Call the shared parent mechanics with split ranking inputs, raw candidate inputs and exact-RVOL series; then validate split semantics (`:206-229`).
3. Require decision-time/symbol ordering, create the source hash chain and bind policy/profile identities (`:360-415`).
4. Persist the eligibility/knowledge boundary and revalidate the finished artifact (`:416-454`).
5. For the new-panel fixture route only, validate synthetic symbols/scope before deriving activations and authenticated Micro triggers (`early_pullback_panel_sources_v01.py:202-235,263-326`).

The captured exact-RVOL source is deliberately **not** listed as an implemented input edge: its registration still disclaims completed exact-RVOL integration (`candidate_rvol_exact.py:87-89`). A real-source adapter remains future work.

## If you change this

- **Hits:** Candidate eligibility/timing, ranking, source fingerprints and every downstream activated replay population.
- **Does not hit:** Provider launch authority, account mechanics or retrospective labels. It cannot turn the synthetic panel fixture into a historical backtest merely by changing its name.

## Surfaces

| Surface | Role |
|---|---|
| V0.3 scanner builder | Reads validated canonical inputs |
| Snapshot/manifest builder | Writes ordered, hashed evidence |
| Synthetic source binder | Exercises the scanner on fixture-only membership |
| Real-source new-panel adapter | Not yet implemented by this route |

## See

- Object: [Causal scanner](../objects/causal-scanner.md)
- [Owning source](../../../src/momentumbot/causal_scanner_snapshot_v03.py)
- [Synthetic binder](../../../src/momentumbot/research/early_pullback_panel_sources_v01.py)
- [Capture boundary](../../../src/momentumbot/research/candidate_rvol_exact.py)
