# Change — historical RVOL basis diagnostic

Status: implemented; code object `3cc1ba86d1e0480c468b741e706972dfd843b0c8`.
Parent and authority: [scope](01_scope.md). No scope expansion.

| Path | Change / consumer |
|---|---|
| `src/momentumbot/research/candidate_rvol_basis_diagnostic.py` | Sealed-failure selection, original page revalidation, request compatibility, exact descriptive OHLC/V/N comparisons and parent-discrepancy reproduction |
| `scripts/audit_candidate_rvol_basis.py` | Saved-source-only runner with external-I/O denial and fresh-output requirement |
| `tests/test_candidate_rvol_basis_diagnostic.py` | Ten deterministic unit tests including malformed data, incomplete history, tampering and no-promotion behavior |
| `tests/test_candidate_rvol_basis_evidence.py` | Two frozen evidence checks without provider/archive replay |
| `research/data-audits/early-pullback-candidate-rvol-basis-diagnostic-v0.1/` | New sealed child report, original run/test logs and reproduction instructions |
| `docs/research/candidate_rvol_basis_diagnostic.md` | Observations, documented `asof` semantics and unresolved correction boundary |

Reused pinned readers, existing parsers, exact volume comparator, seals and
offline audit hook. Original source files, captures, reports, selected/excluded
populations and runtime/risk rules are unchanged. No multiplier is estimated or
applied. Full OHLC rollups are descriptive, not a new acceptance rule.

All 98 historical-session volume disagreements reproduce; 856 affected buckets
also differ in OHLC, with zero trade-count or presence differences. This narrows
the issue but proves neither a provider root cause nor a correction. Both cases
remain withheld. Unknown external consumers remain unknown.

The implementation commit was created without advancing a branch; final
evidence/docs publication advances the branch once for one authoritative CI.
