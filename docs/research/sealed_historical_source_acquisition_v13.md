# Sealed historical source recovery v0.13

## Frozen parent and sole hypothesis

v0.12 run `33929860053`, attempt 1, completed the 706-file checkpoint
validation and all 30 scanner freezes. It then failed at line 259 of
`scripts/run_sealed_historical_source_acquisition_v12.py`: the final runner
used `PARENT_REQUEST_BUDGET` without importing that defined constant. The
permanent failure audit is
`research/data-audits/sealed-historical-source-acquisition-v0.12-run-33929860053-failure-2026-09-06.json`.
The failed run and all older authorizations remain immutable and cannot be
rerun. Only the sanitized failure artifact was uploaded by v0.12; its scanner
outputs are not a recoverable GitHub artifact.

The v0.13 hypothesis is limited to runner wiring and recovery durability:
correctly importing the frozen ledger and executing the real final command
should complete the existing identity-compatible report without changing data
or policy. Undefined-global checks, command-line success/failure regressions,
an early ledger/identity preflight, and a non-final intermediate checkpoint
address the two observed operational gaps. No scanner optimization or strategy
refactor is included.

## Exact retained inputs

- Data parent: v0.10 run `33706372901`, attempt 1.
- Provider checkpoint: artifact `9877181150`, 71,298,708 ZIP bytes.
- ZIP SHA-256: `b13bb68c5c231ba51b73c63d2a0d7e73fa78a0a837d4e35b94a55ddf5006b3b3`.
- Source-checkpoint file SHA-256: `7d1f6858fa669af9de467c36c11e5aff0f3e7af99c0e65bbffcb2814c1040711`.
- Source-checkpoint content hash: `fef36fbcf2844f1da8510572a95c2f2978509bd2b021d2227c03c5ba5f3466f9`.
- Pre-scanner source: 706 files, 572,044,578 bytes; source tree
  `dc95bb478bcb7fdb1b230fa4885402228c82f8614c80fe975a23510ec1922a48`.
- Frozen ledger: 30,522 total attempts (28,831 Alpaca; 1,328 SEC; 363 Massive),
  zero blocked attempts, zero additional provider calls authorized.
- Census: the unchanged exact 30 dates, 946 candidate/float identities,
  737 `composite_figi` and 209 `unique_cik_fallback`.
- Final source layout: 767 files; only 61 scanner files may be added.

## Execution and verification

1. Validate the v0.13 registration and all immutable parent evidence. Check
   every active recovery entrypoint for undefined global references, including
   nested scopes. Run CLI regressions under normal and optimized Python, then
   the full provider-free repository suite.
2. Complete a real-data verification in the hash-pinned CPython 3.12
   environment before installing or launching the new dispatcher. Merely
   importing/compiling the runner, mocked report tests, or a partially finished
   scanner replay is not completed end-to-end evidence. A dedicated research
   push workflow, `sealed-historical-source-recovery-v13-e2e.yml`, can execute
   the multi-hour test durably. It has no manual-dispatch trigger, no market
   credentials, and no final-gate authority. Its report records the real
   research commit, tree, push run and attempt under
   `execution_mode=prelaunch_verification`, always with
   `source_acquisition_gate_passed=false`. Both intermediate and completed
   verification outputs are retained; a completed proof is required before
   the final main dispatcher may be installed. Local reports instead use
   `execution_mode=local_verification`, no GitHub run/dispatcher identity,
   `source_acquisition_gate_passed=false`, and a manual-authorization next gate.
3. A separately authorized manual GitHub attempt 1 checks the exact commit,
   tree, and byte-identical main dispatcher. It downloads only the exact
   retained GitHub artifact, recreates the pinned environment, and deeply
   validates every input file and ledger before reconstructing snapshots.
4. Before the long scanner step, run the actual v0.13 CLI's preflight mode to
   compare the exact request ledger, environment, parent checkpoint, and every
   retained candidate/float identity.
5. Run the inherited v0.10 scanner freeze without credentials. It independently
   rebuilds every date twice, compares exact rows, and reloads persisted bytes.
6. Bind all 767 files and directory entries in
   `v13-recovery/intermediate-checkpoint.json`. Record parent binding, all file
   hashes, source tree, dates, identity preflight, environment, and provenance.
   Upload `sealed-historical-source-v13-intermediate-RUN-ATTEMPT` before final
   deep replay. The receipt explicitly says final validation is pending and
   backtesting is not permitted. Upload failure prevents the final step.
7. Run the actual v0.13 final CLI, retaining the inherited v0.11 scoped identity
   adapter and all strict source-summary checks. Revalidate the intermediate
   source commitment before and after final replay. Only the successful manual
   GitHub execution can produce a final-gate report. Upload the full bundle and
   independently verify the GitHub ZIP digest, all source hashes and the report.

All scientific commands run through `scripts/run_offline_python_v13.py`.
Python audit events block sockets and child processes; the guard is separate
from permitted package installation and GitHub artifact transfer. The scanner
wrapper accepts only `freeze-snapshots`, never the acquisition phase.

Preserve failure accounting even if final reporting fails. The intermediate
cannot automatically authorize a rerun or become a final artifact: any future
reuse requires a separately hash-bound recovery decision.

## Pre-publication verification checkpoint

On 2026-09-06, the hash-pinned local CPython 3.12 environment passed all
1,393 repository tests and the 44-test focused suite under both normal and
optimized Python. The undefined-name gate detects the original, unchanged
v0.12 missing import and passes all five active v0.13 entrypoints. CLI tests
execute the real report builder and complete report validator; intermediate
tests independently hash a synthetic 767-file tree and reject changed bytes,
directory entries, identity counts, ledger values, scanner completion and
rehashed final-eligibility claims. These tests are not real-market replay proof.

The actual offline v0.13 early-preflight command also passed against a fresh
extraction of the exact v0.10 ZIP: all 706 files, the unchanged 30,522-request
ledger and all 946 identities. An older scratch copy containing one extra
temporary file was rejected and left untouched. Local preflight uses explicit
non-final provenance and does not claim a clean, completed GitHub execution.
The complete 30-date real-data end-to-end result remains pending; publication
starts its durable verification workflow, not the final manual recovery.

## Unchanged causal boundary

No provider credentials, market/SEC/news reacquisition, Databento calls,
account/order endpoints, transcript record values, Ross labels/outcomes,
threshold changes, Micro/account policy changes, or policy promotion are
authorized. Research pushes run validation only. After a verified final
Snapshot, the next separate gate remains label-blind scanner/Micro runtime;
retrospective comparison follows frozen runtime results, never precedes them.
