# Saved-source RVOL basis diagnostic

This additive child preserves the original source integration and its two
withheld cases. No provider request, ratio repair or runtime promotion.

- Implementation: `3cc1ba86d1e0480c468b741e706972dfd843b0c8`.
- Parent integration seal: `0a65a01ff43fa5e7c8b72d02bc6f960dc99dd1daae1e92bf17c7430e71bff2a0`.
- [Diagnostic](diagnostic/basis-diagnostic.json.gz): 70,889 bytes,
  SHA-256 `ec532567c2ea6fb7148c787072020326c96d281192f150f138de82dc18cdbb2b`.
- Content seal: `cfe4fa96d7685754effe5539030ac3257cb0045fbaf6aacecde71d09e8526d89`.
- [Execution log](audit.log): optimized-mode audit, 100 prior sessions,
  98 sessions / 856 buckets with both price and volume differences.
- Every selected source root, response-body hash and original capture timestamp
  is retained in the report. Original complete archive bytes and hosted proofs
  are pinned by the reused readers; archive recovery is documented in the
  [parent](../early-pullback-candidate-rvol-exact-source-v0.1/README.md).

With the package installed (or `PYTHONPATH=src`), run from the repository root:

```bash
python -O scripts/audit_candidate_rvol_basis.py \
  --exact-capture /path/to/exact-capture.zip \
  --coarse-capture /path/to/coarse-capture.zip \
  --output /path/to/fresh-output-directory
```

The runner refuses existing output directories and installs the existing
network/process-denying audit hook. It mechanically selects sealed failures,
revalidates both source roots per session, checks request compatibility and
requires exact reproduction of the parent's volume diagnostics. OHLC rollups
are descriptive; even a match cannot certify adjustment vintage or authorize
correction. MGN/2026-03-25 and RUBI/2026-05-19 remain withheld.

Interpretation: [research note](../../../docs/research/candidate_rvol_basis_diagnostic.md).
