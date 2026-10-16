---
type: object
id: object-workflow-control
title: "Hosted workflow and provenance controls"
cluster: development-and-operations
universe: live
status: verified
entity: src/momentumbot/research/hosted_source_gate.py
verified_at: 2026-10-16
verified_commit: 53989a5f1637e759a3922980b40f24cbfbaab5fb
sources: ["src/momentumbot/research/hosted_source_gate.py:15-88", ".github/workflows/candidate-rvol-exact.yml:1-114", ".github/workflows/ci.yml:1-20"]
---

# Hosted workflow and provenance controls

`hosted_source_gate.py` binds a bounded provider operation to exact-code CI, an authorized first attempt, durable consumption and original artifact provenance.

## Why this shape

A passing test run for another revision cannot authorize the current capture, and clicking rerun must not quietly spend the same one-use authorization twice. The gate requires a clean exact child commit, the designated repository/branch/push event, attempt one, matching workflow code and an active authorization window (`hosted_source_gate.py:15-26`). A permanent consumed reference must resolve to the same commit (`:29-31`).

## Shape

Preflight preserves the CI facts, contract, launch identity and bounded file inventory. Verification checks those bytes plus the live consumption reference, artifact identity, run, branch, size, digest and required job outcomes (`:46-88`). The exact-RVOL workflow separates consume, credential-bearing capture and credential-free independent verification. Its capture upload runs even on failure, preserving original failure evidence (`candidate-rvol-exact.yml:15-114`). General CI installs the package, runs the unittest suite and compiles source/tests (`ci.yml:7-20`).

“Live” means these are exercised/reusable controls. An old, consumed or expired registration is not newly usable authorization. Documentation maintenance must not retrigger a market capture by modifying its registered trigger path.

## Connected to

- **owns:** Launch/provenance checks and hosted job coordination.
- **owned-by:** Exact frozen registration and GitHub workflow configuration.
- **joins:** [Source capture](source-capture.md) uses these gates before credentials are loaded; all components rely on CI for code checks.
- **looks-like-but-is-not:** A trading approval, automatic strategy promotion or evidence that every optional dependency was exercised.

## If you change this

- **Hits:** Which jobs may run, evidence required before provider access, artifact acceptance, retries and failure preservation. Contract file hashes may require a separately registered child.
- **Does not hit:** Scanner formulas, setup policy, account risk or the meaning of retrospective metrics. Passing CI is not proof of profitability or complete source integration.

## Surfaces

| Surface | Role |
|---|---|
| General CI | Runs code tests and compilation |
| Consume job | Checks exact-code authority and commits one-use proof |
| Capture job | Receives provider credentials only for bounded capture |
| Verify job | Replays original artifacts without provider credentials |

## See

- [Gate owner](../../../src/momentumbot/research/hosted_source_gate.py)
- [Exact-RVOL workflow](../../../.github/workflows/candidate-rvol-exact.yml)
- [General CI](../../../.github/workflows/ci.yml)
- [Bounded-capture movement](../processes/bounded-capture.md)
