# Verification — source preservation and prior daily input

Source implementation commit: `c6ccce6155d02d3f0868784a9be646d2437698e7`.
Parent `6af2d8176c2b2066402a0ca7f2404c5e0881220e` passed full CI
[38975719878](https://github.com/RoomyRems/momentumbot/actions/runs/38975719878):
3,115 tests, 73 skipped, compilation passed. That is a parent result only.

## Observed local results

- `PYTHONPATH=src python -m unittest tests.test_candidate_daily_source tests.test_source_preservation_inventory tests.test_candidate_daily_history -v`:
  20 passed in 8.530s; [original log](focused-tests.log).
- The same command under `python -O`: 20 passed in 8.265s;
  [original optimized log](focused-tests-optimized.log).
- `PYTHONPATH=src python -O scripts/audit_candidate_daily_source.py --daily-capture ORIGINAL_DAILY_ZIP --output FRESH_DIRECTORY`:
  original pinned bytes, zero external/provider requests, 30 dates, 318,519 bars,
  4,018 exact prior-close matches, 3,904 available original average volumes.
  [Original audit log](../../../../research/data-audits/early-pullback-candidate-daily-source-v0.1/audit.log)
  and [sealed report](../../../../research/data-audits/early-pullback-candidate-daily-source-v0.1/audit/daily-source-audit.json.gz).
- Report seal `c283ae904b3d8924d818aba1da8887476db30d1f5291450993cc855698b1e0c1`;
  compressed bytes 166,974; SHA-256 `41be56526b97979434fdea382c365bec15845fb706ededfcf86a80336d5d88bd`.
- All nine recovered originals matched original proof pins; all nine ordered
  saves succeeded with file identities retained. Offline inventory tests validate
  proof references and Git-backed bytes; they cannot independently prove remote
  file durability. No original was deleted or replaced.

Focused failures cover altered bytes/summaries, duplicate candidates, missing
dates, future/naive/duplicate session timestamps, invalid prices, tiny exact price
differences, missing witnesses and short histories. No local full suite repeated.

## Documentation review and hosted gate

Reviewed the new reader and audit consumer against frozen daily projection and
existing member reads. Only the source-capture card adds source claims; existing
source files and safety boundaries are unchanged. Cold-walk: root context →
status → this run/source card → new reader and preserved report/recovery inventory.
ICM source acceptance, navigation generation and checks passed after this review;
the inspected lock diff contains only the updated source-capture card and new
daily reader. Generated navigation adds the actual new files, with no moved or
deleted frozen paths. `git diff --check` passed. Full hosted CI for the published descendant is
pending at this pre-publication record. Read its exact run result before any
provider job or policy promotion; this work authorizes neither.
