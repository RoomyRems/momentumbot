# Verification — historical RVOL basis diagnostic

Status: focused checks and offline evidence passed; final hosted CI must be
checked on the published evidence commit. A code object alone is not a CI pass.

Scope/change: [scope](01_scope.md), [change](02_change.md).
Implementation: `3cc1ba86d1e0480c468b741e706972dfd843b0c8`; frozen evidence tests
are additive in the publication child. No pre-existing source code changed.

## Observed checks

From the repository root, with `PYTHONPATH=src`:

```bash
python -m unittest tests.test_candidate_rvol_basis_diagnostic tests.test_candidate_rvol_basis_evidence tests.test_candidate_rvol_exact_source tests.test_candidate_rvol_exact_source_evidence -v
python -O -m unittest tests.test_candidate_rvol_basis_diagnostic tests.test_candidate_rvol_basis_evidence tests.test_candidate_rvol_exact_source tests.test_candidate_rvol_exact_source_evidence -v
```

Both passed: 25 tests, zero skipped. Logs:
[normal](../../../../research/data-audits/early-pullback-candidate-rvol-basis-diagnostic-v0.1/focused.log),
[optimized](../../../../research/data-audits/early-pullback-candidate-rvol-basis-diagnostic-v0.1/focused-optimized.log).

The optimized offline runner used only the original pinned exact/coarse ZIPs,
with the existing network/process-denying audit hook. [Audit log](../../../../research/data-audits/early-pullback-candidate-rvol-basis-diagnostic-v0.1/audit.log)
records 100 prior sessions and exact reproduction of 98 mismatching sessions.
Its [sealed output](../../../../research/data-audits/early-pullback-candidate-rvol-basis-diagnostic-v0.1/diagnostic/basis-diagnostic.json.gz)
records 856 buckets with both price and volume differences, no trade-count or
presence differences, and no correction authorization. Original parent evidence
checks also passed. No full local suite or provider capture was run.

Initial local checks caught a Timestamp passed to the JSON-only `exact` helper
(two unit-test errors and an audit error); replaced it with explicit timestamp
equality before the implementation commit. An initial runner invocation omitted
`PYTHONPATH=src` before package installation and stopped at import. These were
local development failures, not source acceptance failures or provider runs.

## Cold walk and preservation

Read root context → status → source-capture card → diagnostic source/research
note. The route identifies sealed inputs, immutable parent, withheld output,
next saved-source audit and fresh-acquisition authority boundary. Only this
affected slice was reviewed; not an exhaustive map audit.

The source-capture card was reviewed against the unchanged source adapter and
new diagnostic before accepting its new source/card fingerprint. The diagnostic
is not a scanner edge, risk change or correction service. Other source claims
remain unchanged. Frozen research evidence is additive only.

`python scripts/maintain_icm.py --accept-reviewed-sources`, `--write` and
`--check` passed; the lock diff affects only the reviewed source-capture card
and the new diagnostic source fingerprint. `git diff --check` passed.
The tracked diff leaves every pre-existing research/data-audit and source file
unchanged; new diagnostic products are additive.

For the final
full gate, inspect the exact published commit's CI run, not merely the source
object or a parent's pass. The prior parent `901ac7c` passed run `38963577181`;
that result does not accept this child.

## Remaining uncertainty

The provider's root cause and a safe common-basis correction remain unproven.
Both cases stay withheld. Completing a diagnostic is not complete daily/minute
basis, float/news, scanner, discretionary integration or strategy acceptance.
