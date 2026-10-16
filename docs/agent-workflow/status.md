---
type: status
status: rvol-history-basis-diagnosed-two-cases-remain-withheld
observed_at: 2026-10-16
source_commit: 3cc1ba86d1e0480c468b741e706972dfd843b0c8
---

# Current observed state

The active development branch is `phase-3-historical-snapshot`.
This record is the current handoff; old checkpoint headings describe their dates.

## Research checkpoint

The [exact-minute capture](https://github.com/RoomyRems/momentumbot/actions/runs/35408612330)
completed successfully on September 19, 2026. All consume, capture and independent
verify jobs passed at code `53989a5f1637e759a3922980b40f24cbfbaab5fb`.
Its [full CI](https://github.com/RoomyRems/momentumbot/actions/runs/35408612252) passed.
These are observed hosted outcomes, not a new local replay or scanner promotion.

[Terminal metadata](runs/icm-adoption-2026-10-16/capture-terminal.json) records the
original job and artifact identities. Capture artifacts were unexpired when checked
and are scheduled to expire December 18, 2026. Preserve accepted source evidence
before retention expiry; never rerun this consumed capture merely to recover files.

## Current development

The [basis diagnostic](runs/rvol-basis-diagnostic-2026-10-16/CONTEXT.md) is the
latest work item. It reproduces all 98 withheld historical-session failures:
856 buckets differ in both OHLC and volume while trade counts and presence
match. Exact histories were captured September 19 and coarse histories September
17. Compatible `asof`/split/SIP parameters do not prove a common adjustment
vintage. No safe correction is established; both cases remain withheld.
The diagnostic and its source lineage are preserved as additive child evidence.

The previous [exact-RVOL source work record](runs/exact-rvol-source-2026-10-16/CONTEXT.md)
owns the unchanged integration. Its optimized offline audit covers
all thirty dates and all 3,309,900 captured bars. It reconciles the eight target
refreshes and produces 159,079 exact RVOL observations for 2,101 of 2,103 retained
cases. MGN/2026-03-25 and RUBI/2026-05-19 remain withheld: 48 and 50 historical
sessions respectively disagree with the coarse source. No fitted rescaling.

The original proof and thirty sealed per-date outputs are preserved in the
exact-source audit directory. The
[verification record](runs/exact-rvol-source-2026-10-16/03_verification.md)
freezes observed local checks. That checkpoint at `901ac7c` passed full CI
[38963577181](https://github.com/RoomyRems/momentumbot/actions/runs/38963577181):
3,103 tests, 73 skipped. For the new diagnostic, inspect the published branch
head's CI result and its [verification record](runs/rvol-basis-diagnostic-2026-10-16/03_verification.md).
No provider request or trading-policy change occurred in either work item.

[Prior ICM adoption](runs/icm-adoption-2026-10-16/CONTEXT.md) is complete at
`972e7d5`; its full CI passed 3,090 tests with 73 optional skips. All 111 routes
and the existing safety boundaries remain preserved.

## Next research step

The saved-source investigation is complete within its evidence limits. Keep
MGN/2026-03-25 and RUBI/2026-05-19 quarantined until independent source evidence
ties target and history to a common basis; neither a fitted scale nor matching
target mornings establishes that. Continue the saved daily/raw/split basis audit
across the existing candidate population without case-specific fitting. Fresh
verification, if required, needs a new bounded registration and fresh authority;
do not rerun a consumed capture. Then continue historical float/news, the complete
captured-source scanner adapter and scanner-to-shadow integration only when
their actual inputs verify. Exact RVOL is a completed input component for the
ready cases, not a claim of full scanner or discretionary readiness.
Start with [source capture](../map/objects/source-capture.md) and
[scanner reconstruction](../map/processes/scanner-reconstruction.md).

The original acquisition authorization window has expired. This handoff grants
no new provider run, subscription, order or live-money authority. Existing
shadow assessments remain descriptive, not an active trading decision service.

## Preserved history

[September checkpoint history](../project/current_state_2026-08-31.md) remains
unchanged. [Earlier checkpoint](../project/current_state.md) is also retained,
but is not the current task router.
