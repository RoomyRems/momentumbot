# Sealed historical management exit acquisition v0.1

This unarmed child of `0d36c619dc1d3ac8c50bf7fa91201114255e696c` registers
acquisition of the exact 80 requests from verified quote run `34169338681`.
The hypothesis is that these missing common exit sources can be captured while
preserving the original entry evidence and reusing the already verified XAGE pair.
Ross fills, recap labels and retrospective outcomes remain sealed.

The [contract](../../research/strategy/sealed-historical-management-exit-acquisition-v0.1.json)
and [individual limits](../../research/runtime/sealed-historical-management-exit-acquisition-v0.1/request-limits.json)
bind the complete verified quote, both retained quote ZIPs and all 19 members.
Total billable size cannot exceed **209,898,320 bytes**, and the re-quoted total
cannot exceed **$0.234732925899 USD**. Each request also has its own original size
and cost ceiling. Savings on one request cannot offset an increase on another.
These are preflight quote limits; actual provider billing is not inferred.

The harness permits at most 160 metadata calls followed by 80 time-series calls,
with no retries, redirects, extra parameters or substituted request bounds.
Every metadata result must pass before any download. Per-request wire size is
bounded by the original billable size plus 65,536 bytes. Existing limits remain
400 MB decompressed native data per request, 1 GB retained output and 1.5 GB
normalized data, with a 16 MB metadata/archive reserve.

Native decoding, exact symbol/session mapping, record-order normalization and
bounded HTTP methods are inherited from the frozen acquisition parents.
Quote tapes preserve original per-request record ordinals and native order.
An exact metadata-only response with zero native and normalized records produces
an explicit unavailable receipt and no empty tape. A transport, truncation,
mapping, normalization or write failure stops the sequence and retains partial
evidence as ineligible. Every unattempted request remains in the 80-row coverage
report. Temporary cleanup must succeed before complete evidence can be reported.

All 109 original opportunity classifications, including 23 unavailable entries,
are copied unchanged into the capture report. The XAGE reuse proof remains bound
to the original pair and original source intervals. New exit data cannot rescue
an unavailable entry or replace an entry price. The original 30,522-request
source ledger remains separate from this prospective acquisition ledger.

The workflow runs provider-free validation on a code push. Provider access needs
a sole added execution record bound to its immediate code parent, exact tree,
workflow bytes, successful CI and dedicated validation on attempt one. Both quote
artifacts and main plus all 15 prior consumed references are checked before an
atomic new consumed reference and durable consumption upload. Only the following
step receives the provider credential. Complete or partial evidence is retained.

The [registration audit](../../research/data-audits/sealed-historical-management-exit-acquisition-v0.1-registration-2026-09-07.json)
records local tests, exact parent archive verification, independent stdlib
verification and reproducible synthetic captures using the real pinned SDK.
The independent checker separately checks request limits, archive inventory,
receipt/tape bytes, record populations and ordering. The primary verifier also
enforces the frozen native schema and normalization semantics.

No execution record is added by this registration. No real provider request,
purchase, historical replay, account simulation or retrospective access occurred.
Complete captured source evidence would still require independent verification
and a registered composer before runtime eligibility. Historical fees, sell-ledger
reconciliation, authenticated account-state production, causal next-session
valuation, continuous account/order integration and a historical execution child
remain separate unresolved dependencies.

Provider-free registration check:

```bash
PYTHONPATH=src:scripts python scripts/acquire_sealed_historical_management_exit_inputs_v01.py --validate-only
python scripts/verify_sealed_historical_management_exit_acquisition_registration_v01.py
```

Use `--verify-parents --preflight-root <directory>` to verify the two exact quote
ZIPs. The CLI `--verify-capture --output-root <directory>` verifies a retained
capture against its execution record. These verification modes make no provider
requests. Hosted execution requires CPython 3.12.14 and the existing 29 hash-locked
dependencies; local tests use CPython 3.12.13 with those same package versions.
