---
type: process
id: process-scanner-reconstruction
title: "Reconstruct causal scanner dispositions"
cluster: candidate-discovery
universe: live
entity: src/momentumbot/causal_scanner_snapshot_v03.py
verified_at: 2026-10-16
verified_commit: b83b5dba644cc237ed1cb41fc10dc59b27c65995
sources: ["src/momentumbot/causal_scanner_snapshot_v03.py:183-229", "src/momentumbot/causal_scanner_snapshot_v03.py:350-454", "src/momentumbot/research/early_pullback_panel_sources_v01.py:202-235", "src/momentumbot/research/early_pullback_panel_sources_v01.py:263-326", "src/momentumbot/research/candidate_rvol_exact.py:87-89", "src/momentumbot/research/candidate_rvol_exact_source.py:163-214"]
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

The original capture registration still disclaims completed integration
(`candidate_rvol_exact.py:87-89`). Its additive exact-source adapter now reconciles
all supplied target/history inputs and emits exact aligned curves only when
they agree (`candidate_rvol_exact_source.py:163-214`). This supplies one source
component; a complete real-source scanner adapter remains future work, including
daily/minute price/share-basis agreement and historical float/news evidence.

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
- [Exact-RVOL integration](../../../src/momentumbot/research/candidate_rvol_exact_source.py)
