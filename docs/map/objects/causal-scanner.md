---
type: object
id: object-causal-scanner
title: "Causal scanner snapshot"
cluster: candidate-discovery
universe: live
status: verified
entity: src/momentumbot/causal_scanner_snapshot_v03.py
verified_at: 2026-10-16
verified_commit: b83b5dba644cc237ed1cb41fc10dc59b27c65995
sources: ["src/momentumbot/causal_scanner_snapshot_v03.py:39-81", "src/momentumbot/causal_scanner_snapshot_v03.py:183-229", "src/momentumbot/causal_scanner_snapshot_v03.py:350-454", "src/momentumbot/research/early_pullback_panel_sources_v01.py:202-235", "src/momentumbot/research/early_pullback_panel_sources_v01.py:263-326", "src/momentumbot/research/candidate_rvol_exact_source.py:163-214"]
---

# Causal scanner snapshot

The v0.3 scanner is a deterministic candidate-minute disposition tape with explicit raw-price and split-adjusted ranking semantics.

## Why this shape

A candidate's displayed price and volume cannot silently share the adjustment basis of gain and cross-sectional rank. V0.3 preserves raw candidate observations while calculating gain/rank against split target closes and split previous closes; equal timestamps do not imply equal prices across bases (`causal_scanner_snapshot_v03.py:50-81`).

## Shape

Inputs include full resolved membership, candidate rows, previous closes, split ranking frames, raw candidate frames, exact-RVOL curves, float and news evidence. `build_scanner_snapshot_rows` delegates shared mechanics to v0.2 and then revalidates split consistency (`:183-229`); older modules here are live ancestors, not dead replacements. Artifact construction fixes canonical decision-time/symbol order and source hashes. It explicitly denies universe completeness, full walk-forward eligibility and policy promotion (`:360-454`).

The new-panel adapter remains synthetic: it requires `SYNTHETIC` membership and the synthetic scope (`early_pullback_panel_sources_v01.py:202-235,263-267`). The real captured-source-to-new-panel adapter is a **ghost integration**, not an existing completed production route.

The separate [exact-RVOL source adapter](../../../src/momentumbot/research/candidate_rvol_exact_source.py)
now produces reconciled minute curves. This is one input component; it does not
complete the real-source new-panel route or supply missing float/news evidence.

## Connected to

- **owns:** Candidate dispositions and source-basis semantics, not provider acquisition.
- **owned-by:** Frozen scanner/profile policies and evidence supplied by [source capture](source-capture.md).
- **joins:** Qualified activations feed [Micro replay](micro-replay.md); structured decision facts can feed [context shadow](context-shadow.md).
- **looks-like-but-is-not:** The older public-CLI scanner/backtester is a separate baseline path.

## If you change this

- **Hits:** Candidate timing, rank, eligibility, activation identity, snapshot fingerprints, downstream replay populations and comparison denominators.
- **Does not hit:** Actual source authorization, Micro order simulation rules, account risk limits or the shadow's lack of trading authority. Captured bars alone do not satisfy float/news inputs.

## Surfaces

| Surface | Role |
|---|---|
| V0.3 builders/validators | Construct and revalidate frozen rows and manifests |
| Synthetic panel binder | Supplies fixture-only inputs and derives activations |
| Micro consumers | Read qualified activations, not later evaluation labels |
| External snapshot consumers | Unknown; preserve versioned paths |

## See

- [Owning source](../../../src/momentumbot/causal_scanner_snapshot_v03.py)
- [Synthetic panel binder](../../../src/momentumbot/research/early_pullback_panel_sources_v01.py)
- [Scanner reconstruction](../processes/scanner-reconstruction.md)
