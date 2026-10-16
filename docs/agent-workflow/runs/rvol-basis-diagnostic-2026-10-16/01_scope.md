# Scope — historical RVOL basis disagreement

Status: scoped under the owner's “Continue” request on October 16, 2026.

## Working inputs

- Parent: `RoomyRems/momentumbot`, `phase-3-historical-snapshot`,
  `901ac7c710728d3a71fe513f775e5541ca145a95`; clean local and matching remote head.
- [Previous handoff](../exact-rvol-source-2026-10-16/04_handoff.md).
- [Source capture card](../../../map/objects/source-capture.md) and
  [scanner reconstruction](../../../map/processes/scanner-reconstruction.md).

## Intended result and impact

Hypothesis: the two withheld cases have price as well as volume differences
between saved 1Min and 15Min histories, despite compatible request parameters.
Determine the observed differences and whether saved evidence establishes a
safe correction. No inferred multiplier, tolerance fit or case-specific policy.

Add one research diagnostic module, offline runner, focused tests, a versioned
child evidence directory and workflow/navigation notes. Reuse existing pinned
archive readers and volume comparator. Select cases mechanically from the
sealed parent failures; inspect all fifty prior sessions, including empty ones.
Preserve requests, response hashes, capture timestamps and per-bucket values.

No existing source adapter, frozen evidence, acquisition selector, strategy,
runtime, risk or order interface changes. Unknown external consumers remain
unknown. No Ross/recap labels, fills, future outcomes or transcript inputs.

## Acceptance and authority

- Reproduce the parent's exact volume discrepancies; reject altered/missing
  sources, dates, coverage or incompatible requests. Do not call a match proof
  of daily/minute share-basis correctness.
- Focused unit tests normal and optimized, offline saved-source diagnostic,
  ICM checks and one authoritative full CI at the published commit.
- Existing continuation covers offline development/publication. Original capture
  authorization remains expired and consumed; no new provider call, subscription,
  dataset expansion or live/financial authority follows from this work.
- No new human decision needed within this scope. If sources do not prove a
  correction, preserve quarantine and specify the missing evidence.
