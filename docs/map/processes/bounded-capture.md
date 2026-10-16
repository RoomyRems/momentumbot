---
type: process
id: process-bounded-capture
title: "Acquire and verify bounded original data"
cluster: market-data
universe: live
entity: src/momentumbot/research/candidate_rvol_exact.py
verified_at: 2026-10-16
verified_commit: 53989a5f1637e759a3922980b40f24cbfbaab5fb
sources: ["src/momentumbot/research/candidate_rvol_exact.py:72-163", "src/momentumbot/research/hosted_source_gate.py:15-88", ".github/workflows/candidate-rvol-exact.yml:15-114"]
status: verified
consumes: ["docs/map/objects/workflow-control.md", "docs/map/objects/source-capture.md"]
produces: ["docs/map/objects/source-capture.md"]
---

# Acquire and verify bounded original data

This movement turns a frozen exact-minute request registration into original capture bytes and an independently checked provenance proof.

## Input → Movement → Output

Input is the pinned selection audit, exact requests, clean authorized child and same-code CI evidence. Consume, capture and verify run as separate first-attempt jobs, carrying hashes and original artifact metadata between them. Output is source evidence with explicit integration limitations, not a scanner feature tape.

## Why this shape

Repeated provider requests can spend authorization or change data vintage. A durable consumed reference prevents reuse, and verification reads the original archive without provider requests. Completion of transport/protocol checks cannot establish daily/minute share-basis consistency or exact same-time RVOL semantics.

## Steps

1. Recompute and validate the registered roots against the accepted audit, including unresolved target rechecks (`candidate_rvol_exact.py:72-95`).
2. Validate the authorization window, first-attempt workflow identity and permanent consumed commit; preserve exact-code CI preflight (`hosted_source_gate.py:15-78`).
3. Load provider credentials only after preflight, require a fresh output path and process bounded split one-minute responses (`candidate_rvol_exact.py:98-151`).
4. Preserve original success or failure in the hosted capture job (`candidate-rvol-exact.yml:44-82`).
5. Revalidate jobs, artifacts and original pages in the separate verifier. The proof still sets the two RVOL integration flags false (`candidate_rvol_exact.py:154-163`).

## If you change this

- **Hits:** Provider scope, spending/retry boundaries, source vintage, completeness proof, registration fingerprints and downstream source trust.
- **Does not hit:** Scanner activation, Micro setup selection, account trades or any live-order permission. Expired/consumed contracts are not reusable capture authority.

## Surfaces

| Surface | Role |
|---|---|
| GitHub consume job | Writes one-use launch proof after exact CI |
| Capture runner | Writes original response evidence |
| Independent verifier | Reads original artifacts and writes proof |
| Future source adapter | Must separately establish feature semantics |

## See

- Objects: [Source capture](../objects/source-capture.md), [workflow control](../objects/workflow-control.md)
- [Owning source](../../../src/momentumbot/research/candidate_rvol_exact.py)
- [Hosted gates](../../../src/momentumbot/research/hosted_source_gate.py)
- [Job ordering](../../../.github/workflows/candidate-rvol-exact.yml)
