# Handoff — exact-minute RVOL source integration

Status: source adapter and sealed integration delivered; two source cases withheld.

## Outcome

The original exact capture is integrated into an offline reader and exact RVOL
projection. All eight registered target refreshes reconcile. Of 2,103 retained
cases, 2,101 produce 159,079 exact RVOL observations. MGN/2026-03-25 and
RUBI/2026-05-19 remain unavailable because their historical volume sources differ.
They were not normalized or silently dropped from the report.

## Evidence and publication

- [Scope](01_scope.md), [implementation](02_change.md), [verification](03_verification.md).
- Implementation commit: `b83b5dba644cc237ed1cb41fc10dc59b27c65995`.
- Accepted original proof and per-date child outputs are under
  `research/data-audits/early-pullback-candidate-rvol-exact-source-v0.1/`.
- This handoff is included in the child evidence/navigation commit. Its exact
  branch head and hosted CI run are authoritative; this record is written before
  branch publication and does not predeclare hosted success.

## Next action

Investigate the 98 historical-session differences for the two withheld cases,
using their preserved exact/coarse request and response evidence first. No new
capture is implied or currently authorized by the consumed registration.
Continue daily/minute price/share-basis, historical float/news and the complete
captured-source scanner adapter before scanner-to-discretionary integration.
The [canonical status](../../status.md) now routes directly to this work item.

The source integration is not scanner readiness or strategy promotion. Risk,
policy, broker authority and transcript/runtime separation remain unchanged.
Original archives are subject to their existing GitHub retention windows;
preserved proof and derived outputs do not authorize repeating an expired capture.
