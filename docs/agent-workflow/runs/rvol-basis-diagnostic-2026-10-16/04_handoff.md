# Handoff — historical RVOL basis diagnostic

Status: diagnostic complete within saved-source scope; correction unresolved.

The new child evidence traces both withheld cases through all 100 prior
sessions. It reproduces the 98 historical volume failures and establishes that
all 856 affected buckets also have OHLC differences despite matching trade
counts and bucket presence. No safe correction follows from those observations.
MGN/2026-03-25 and RUBI/2026-05-19 remain withheld; the 2,101 ready cases and
every frozen parent/source/runtime/risk artifact remain unchanged.

## Evidence and publication

- [Scope](01_scope.md), [implementation](02_change.md), [verification](03_verification.md).
- Implementation object: `3cc1ba86d1e0480c468b741e706972dfd843b0c8`.
- This record accompanies its evidence/docs child on
  `RoomyRems/momentumbot:phase-3-historical-snapshot`. Verify the final published
  commit's CI check; the implementation object did not advance a branch alone.
- Local normal/optimized focused checks passed 25 tests each. Full hosted CI is
  a separate gate, not inferred from these checks. No provider job was launched.

## Next action

Audit saved daily/raw/split basis across the existing candidate population with
no fitted ratios or case-specific tolerance. Keep these two RVOL histories
quarantined unless independent evidence ties target and history to the same
basis. New data verification requires a fresh bounded registration/authority,
not a rerun of the consumed captures. Historical float/news, the full source
scanner adapter and discretionary shadow integration remain downstream tasks.

All work here uses existing saved sources; no new subscription, expanded data
population or trading authority. [Canonical status](../../status.md) links this
child and preserves the prior integration's evidence and limits.
