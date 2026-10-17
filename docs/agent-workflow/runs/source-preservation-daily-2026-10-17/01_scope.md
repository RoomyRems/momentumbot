# Scope — preserve sources and integrate prior daily history

Status: scoped under the October 17 owner continuation/preservation request.
Parent branch and clean local/remote head: `phase-3-historical-snapshot`,
`6af2d8176c2b2066402a0ca7f2404c5e0881220e`.

## Inputs and intended result

Read [status](../../status.md), [source capture](../../../map/objects/source-capture.md),
the frozen daily-history registration/projector, original hosted proof and
saved scanner previous-close witnesses. Prior full CI `38975719878` passed
3,115 tests, 73 skipped, plus compilation at this parent.

1. Recover the original exact/coarse, split/raw minute and prior-daily captures
   plus missing consumption evidence. Validate original bytes and preserve the
   non-Git-backed archives outside Actions retention. Inventory Git-preserved
   evidence and already retained transcript attachments without inspecting their
   narratives. Do not duplicate the git repository into file storage.
2. Add a pinned prior-daily archive reader using the frozen daily projector.
   Emit original last-fifty-session inventory and average daily volume, with
   explicit insufficient history. Compare the original saved previous-close
   witness to the daily history on its exact session; no fitted scale or epsilon.
3. Preserve an additive all-date audit and recovery instructions; do not claim
   source-wide preservation beyond the inventory actually checked.

## Boundaries and checks

No provider capture, changed subscription, expanded population, live order,
strategy/risk change, fitted correction or scanner promotion. No transcript,
recap fill/action, evaluation label or future outcome enters runtime features.
Daily/minute share basis remains unverified even if daily closes agree.
Frozen parents and failed evidence remain unchanged. Unknown consumers remain
unknown. New paths are confined to the daily reader, audit/recovery utilities,
focused tests, child evidence and workflow/map records.

Focused normal and optimized tests, hash/pin verification, offline all-date
projection, ICM checks and one exact published-commit full CI. Escalate any
permissions blocker or need for fresh acquisition; no new authority assumed.
