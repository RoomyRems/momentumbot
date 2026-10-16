# Change — exact-minute RVOL source integration

Status: implemented and all-date source integration completed, with two cases withheld.

The [scope](01_scope.md) starts at `972e7d5`. Exact implementation source is
`b83b5dba644cc237ed1cb41fc10dc59b27c65995`; its Git tree is byte-identical to the
tested local source tree. The child evidence/navigation commit publishes this
source revision as its parent; inspect the branch and exact-commit CI for hosted acceptance.

| Path | Change | Purpose |
|---|---|---|
| `src/momentumbot/research/candidate_rvol_exact_source.py` | Pinned proof/archive reader, historical/target reconciliation, exact aligned RVOL projection | Supplies the missing exact-minute source component |
| `scripts/audit_candidate_rvol_exact_source.py` | Offline all-date audit with sealed per-date outputs and aggregate report | Preserves ready and withheld populations with full source lineage |
| `scripts/fetch_candidate_rvol_exact_sources.py` | Read-only recovery of four original GitHub artifacts | Reproduction without market-provider requests |
| `tests/test_candidate_rvol_exact_source.py` | Eleven focused regressions | Covers causality, DST, empty history, missing inputs, tampering, mismatches and target refreshes |
| `tests/test_candidate_rvol_exact_source_evidence.py` | Two frozen-output checks | Binds the report, per-date hashes, accepted curves and explicit withheld cases |
| New exact-source audit directory | Original verification ZIP and child integration evidence | Keeps the original capture proof intact |

The existing calculator, alignment utility, frozen requests, strategy thresholds,
raw prices/execution volume, account rules and capture workflows are unchanged.
No transcript file is opened. The output does not enable the historical scanner,
account evaluation, discretionary decision effects or broker orders.

The audit additionally checks all fifty historical sessions against the coarse
selection source. Any disagreement withholds the case rather than applying an
estimated split multiplier. The captured-history endpoint excludes the 10:00
bar start, so outputs end at 09:59 ET and retain minute-close availability.

There is no implementation scope expansion or new spending. External consumers
remain unknown; all existing paths and interfaces are preserved.

The finished audit reconciles all eight target refreshes and emits 2,101 cases.
MGN/2026-03-25 and RUBI/2026-05-19 are withheld because 98 historical sessions
disagree across the original sources. Their full comparison evidence is retained.
