# Scope — exact-minute RVOL source integration

Status: scoped under the owner's October 16 continuation request.

## Inputs and parent

Parent `972e7d546fb995512fc8837d6e23b4d7e77674b1`, active branch
`phase-3-historical-snapshot`; clean checkout with no existing user edits.
The [status router](../../status.md) identifies exact-RVOL source integration as
the next unfinished task. Original capture run `35408612330` and proof are
byte-pinned; the captured 2,103 cases and eight target refreshes are fixed.

## One change and impact

Add an offline reader, reconciliation and exact same-time RVOL output for the
retained population. Reuse the existing RVOL calculator and raw-index alignment.
Validate all fifty prior sessions against the coarse source used for acquisition;
withhold any disagreement. Refreshes may replace only the eight registered RVOL
target-volume inputs. Preserve all raw-price/execution-volume data and originals.

Editable paths: new `candidate_rvol_exact_source.py`, its focused tests and audit
script, a new source-audit directory, and affected map/status/work-item documents.
Existing capture code, registrations, strategy, account and risk policy are frozen.
The [scanner](../../../map/objects/causal-scanner.md) consumes exact RVOL, but a
complete historical source adapter still requires adjustment-basis/float/news work.
External consumers are unknown; existing interfaces and paths stay in place.

## Acceptance and authority

Focused normal and optimized tests, one offline all-date integration, navigation
maintenance, and one authoritative full GitHub CI run on published code. No
duplicate full local suite. Preserve accepted original proof and reproducible
per-date outputs with hashes. Record unresolved comparisons without promotion.
This is already authorized continuation. No provider capture, subscriptions,
live orders, strategy tuning or outcome-label access is authorized by this work.
