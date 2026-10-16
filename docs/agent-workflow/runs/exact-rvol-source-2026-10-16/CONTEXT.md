# Exact-minute RVOL source integration

Parent: `972e7d546fb995512fc8837d6e23b4d7e77674b1` on `phase-3-historical-snapshot`.
Active stage: integration completed with two withheld cases; publication/CI handoff.

Inputs are the original September 19 exact capture and independent proof,
the frozen coarse acquisition selection, and accepted raw/split/coarse archives.
No transcript records, recap actions, fills or future outcome labels are inputs.

- [Scope](01_scope.md) defines the authorized bounded change.
- [Change](02_change.md): additive exact-source reader and offline audit.
- [Verification](03_verification.md): focused tests, 30-date integration and source review.
- [Handoff](04_handoff.md): actual result, publication boundary and next task.

Result: 2,101 ready cases and 159,079 exact RVOL observations. All eight registered
target refreshes reconciled. MGN/2026-03-25 and RUBI/2026-05-19 remain withheld for
48 and 50 historical-session disagreements respectively. No estimated rescaling.

Next: investigate those historical share-volume differences using the preserved
source evidence, then finish daily/minute price/share-basis, float/news and the
full captured-source scanner adapter before discretionary shadow integration.

The existing capture authorization is consumed; this run requests no provider data.
