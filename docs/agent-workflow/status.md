---
type: status
status: exact-rvol-source-integrated-with-two-withheld-cases
observed_at: 2026-10-16
source_commit: b83b5dba644cc237ed1cb41fc10dc59b27c65995
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

The [exact-RVOL source work record](runs/exact-rvol-source-2026-10-16/CONTEXT.md)
owns the current implementation and evidence. The optimized offline audit covers
all thirty dates and all 3,309,900 captured bars. It reconciles the eight target
refreshes and produces 159,079 exact RVOL observations for 2,101 of 2,103 retained
cases. MGN/2026-03-25 and RUBI/2026-05-19 remain withheld: 48 and 50 historical
sessions respectively disagree with the coarse source. No fitted rescaling.

The original proof and thirty sealed per-date outputs are preserved in the
new exact-source audit directory. The
[verification record](runs/exact-rvol-source-2026-10-16/03_verification.md)
freezes observed local checks; inspect the published branch head's CI check for
its hosted acceptance. No provider request or trading-policy change occurred.

[Prior ICM adoption](runs/icm-adoption-2026-10-16/CONTEXT.md) is complete at
`972e7d5`; its full CI passed 3,090 tests with 73 optional skips. All 111 routes
and the existing safety boundaries remain preserved.

## Next research step

Investigate the two withheld historical-volume cases from the saved sources;
do not treat matching target mornings as proof of historical share-basis agreement.
Then continue daily/minute price/share-basis, historical float/news, the complete
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
