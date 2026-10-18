---
type: object
id: object-source-capture
title: "Bounded source capture"
cluster: market-data
universe: live
status: verified
entity: src/momentumbot/research/candidate_rvol_exact.py
verified_at: 2026-10-17
verified_commit: 80441944c3ac3ab050d13a5d323c76e76a7ab212
sources: ["src/momentumbot/research/candidate_rvol_exact.py:38-89", "src/momentumbot/research/candidate_rvol_exact.py:98-163", "src/momentumbot/research/candidate_rvol_source.py:45-80", "src/momentumbot/research/hosted_source_gate.py:15-78", "src/momentumbot/research/candidate_rvol_exact_source.py:29-147", "src/momentumbot/research/candidate_rvol_exact_source.py:163-214", "src/momentumbot/research/candidate_rvol_basis_diagnostic.py:28-207", "src/momentumbot/research/candidate_daily_source.py:21-112", "src/momentumbot/research/candidate_feature_inputs.py:18-111"]
---

# Bounded source capture

The current acquisition object is the exact-RVOL registration plus its original capture and verification artifacts, owned by `candidate_rvol_exact.py`.

## Why this shape

Provider responses must be attributable to an exact request set, code revision, authorization window and one consumed launch. A successful download is source evidence, not permission to promote its values into a strategy. The coarse selector deliberately retains target-volume disagreements and does not use gain, rank or retrospective outcomes to choose cases (`candidate_rvol_source.py:45-80`).

## Shape

The registration binds the accepted coarse audit, its prepared fifty-session history requests, and same-capture target rechecks. It pins file bytes and inherits bounded runtime and payload rules (`candidate_rvol_exact.py:38-89`). `ExactPages` requires split one-minute bars on the requested observation date; `Capture` enforces the attempt ceiling. The verifier replays original bytes and leaves `daily_minute_share_basis_verified` and `exact_same_time_rvol_complete` false (`candidate_rvol_exact.py:98-163`). Those fields are an integration boundary, not a failed transport claim.

The additive `CandidateExactArchive` accepts the original proof and projects the
fifty-session histories and registered target refreshes without changing the
capture contract. `integrate_case` compares exact and coarse bucket totals,
withholds disagreements and reuses the existing exact-RVOL calculator and index
alignment (`candidate_rvol_exact_source.py:29-147,163-214`). Its child evidence
records source integration separately from the unchanged original capture proof.

The additive basis diagnostic selects sealed failures, revalidates saved pages
and reproduces their volume disagreements while recording OHLC/trade-count
comparisons. Compatible request parameters are not adjustment-vintage proof;
no correction or promotion follows even from a matching comparison
(`candidate_rvol_basis_diagnostic.py:28-207`).

The pinned daily reader reuses the original history projector and last-fifty-session
average. Its same-session previous-close comparison uses exact values, reports
missing witnesses explicitly, and never promotes daily/minute basis agreement
(`candidate_daily_source.py:21-112`). All-date child evidence has 4,018 matching
closes and 3,904 available volume averages, with 114 unavailable histories.
The [recovery inventory](../../agent-workflow/runs/source-preservation-daily-2026-10-17/source-preservation.json)
records nine separately saved originals and five already Git-backed artifacts;
it does not claim exhaustive preservation of all historical Actions runs.

## Connected to

The [joined candidate reader](../../../src/momentumbot/research/candidate_feature_inputs.py)
consumes those byte-pinned daily/exact reports, preserving the complete daily
case population and explicit missing or disagreeing curves. Its completed-bar
helper enforces start plus one minute. It supplies partial inputs only; full
scanner readiness and float/news remain false (`candidate_feature_inputs.py:18-111`).

- **owns:** Request registration, single-use reference, response state and independent archive proof.
- **owned-by:** The frozen acquisition contract and [workflow control](workflow-control.md).
- **joins:** The offline exact-RVOL adapter supplies validated source curves; the full captured-source adapter to [causal scanner](causal-scanner.md) still needs its remaining inputs and checks.
- **looks-like-but-is-not:** Coarse acquisition bounds are not runtime RVOL; source verification is not scanner semantic acceptance.

## If you change this

- **Hits:** Request derivation, parent bindings, consumed-run provenance, capture limits, archive verification and the evidence a future scanner adapter can trust.
- **Does not hit:** Micro setup thresholds, account risk, existing frozen experiment results, or broker-order authority. It does not itself complete historical float/news integration.

## Surfaces

| Surface | Role |
|---|---|
| Exact capture runner | Reads the registration; writes bounded capture artifacts |
| Independent verifier | Reads original bytes; emits provenance proof without provider requests |
| Exact-RVOL source reader/audit | Reconciles saved sources and emits aligned exact curves or explicit disagreement |
| Prior-daily reader/audit | Projects authenticated saved history; exact daily-close agreement is not minute-basis proof |
| Scanner runtime | No direct authorization from these acquisition values |
| External archive consumers | Unknown; do not move evidence paths on that assumption |

## See

- [Owning source](../../../src/momentumbot/research/candidate_rvol_exact.py)
- [Coarse source selection](../../../src/momentumbot/research/candidate_rvol_source.py)
- [Exact-RVOL source integration](../../../src/momentumbot/research/candidate_rvol_exact_source.py)
- [Prior-daily source integration](../../../src/momentumbot/research/candidate_daily_source.py)
- [Withheld-history diagnostic](../../../docs/research/candidate_rvol_basis_diagnostic.md)
- [Hosted launch gates](../../../src/momentumbot/research/hosted_source_gate.py)
- [Bounded-capture movement](../processes/bounded-capture.md)
