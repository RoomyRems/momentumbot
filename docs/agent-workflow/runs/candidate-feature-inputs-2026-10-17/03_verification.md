# Verification

Source commit: `80441944c3ac3ab050d13a5d323c76e76a7ab212`.

- Focused `tests.test_candidate_feature_inputs`: six tests passed normally
  (0.221s) and under `python -O` (0.197s). Original [normal](focused.log) and
  [optimized](focused-optimized.log) logs cover source tampering, duplicates,
  invalid numbers/timestamps, completed-minute timing, DST and withheld cases.
- `PYTHONPATH=src python -O scripts/verify_candidate_feature_inputs.py --output FRESH_PATH`
  passed across all thirty dates with external I/O denied. The
  [report](integration-report.json) and [log](integration.log) retain the original
  result: 4,018 cases, 2,101 joined daily/RVOL cases, two source disagreements,
  1,915 not retained for exact acquisition, and 159,079 RVOL observations.
- Report seal: `3985b1e5d121cfc7c7ecca54625b5681bd60df8987548ad992f2aaef4fc6b235`.

Reviewed the new reader and its verification consumer against immutable daily
and exact reports; only the source-capture map adds claims about this reader.
Cold-walk: status → this work item → owning source and report; full scanner
and unavailable-input boundaries remain explicit. ICM reviewed-source maintenance,
generation and checks passed. The lock diff only adds this reader and updates
its source-capture card; `git diff --check` passed. No local full-suite duplication.
The publishing descendant's full hosted CI is pending at authoring; inspect
its exact run before relying on a hosted pass.
