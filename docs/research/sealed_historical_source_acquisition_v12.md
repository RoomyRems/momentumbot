# Sealed historical source freeze recovery v0.12

## Status and purpose

Run `33928334660` dispatched v0.11 exactly once from `main`. Its provider-free
validation job succeeded, and its freeze job verified the immutable checkout,
dispatcher, exact v0.10 artifact metadata, and artifact download. It then
failed before checkpoint deep validation while comparing the recreated
environment. The step installed MomentumBot into `.venv-v11` but invoked plain
`python` later in the same shell step. GitHub applies additions to
`GITHUB_PATH` only to later steps, so system Python raised
`ModuleNotFoundError: No module named 'momentumbot'`.

The failure is a workflow interpreter-scope mistake, not a provider-data,
credential, request-budget, checkpoint, identity, scanner-freeze, or final
replay failure. No provider call occurred. The retained v0.10 checkpoint
remains unchanged, and the v0.11 safe-failure artifact is preserved as artifact
`9957636441`, ZIP SHA-256
`8b62a18458e05391029ef918833016b5fc62024fda5f333b3f1a710b752aa378`.
v0.11 may not be rerun.

v0.12 is a new provider-free final-freeze child. Its only behavioral repair is
to invoke `.venv-v12/bin/python` explicitly for the same-step environment
comparison. It otherwise inherits the exact v0.11 identity-compatible final
summarizer, exact v0.10 checkpoint, all 706 source files, 30 scanner replays,
946-record identity preflight, and `finally` restoration contract unchanged.

## Exact parents

The immediate failed execution is v0.11 run `33928334660`, attempt 1,
authorization commit `bad5bfb048f3e4d5690038dfc4dd7c9c0968ea63`, tree
`e8bb6290721a93f0904012363ebdff34313ce3e3`, and dispatcher commit
`1a4f9f7bf483c139c4d656b2ab0a23279e8cf769`. It failed closed before deep
checkpoint validation or scanner output. Its permanent failure audit content
SHA-256 is
`c901ff41eda568af3941d4e91adac65b4d7e9d519d2377a8a96e161c734b4a82`.

The data parent remains v0.10 run `33706372901`, attempt 1, authorization commit
`652db5675a35b6f455aa0d924aa50428dd995280`, tree
`48092229da6a5cf2dd24de6fe4f98584e6de68e3`, and dispatcher commit
`8b920876d9a513f31d6fdb6795c4155a2c1a1519`. Its authorization was permanently
consumed before provider access and may not be rerun.

The retained provider checkpoint is artifact `9877181150`, named
`sealed-historical-source-acquisition-v10-provider-checkpoint-33706372901-1`.
Its GitHub ZIP size is 71,298,708 bytes and ZIP SHA-256 is
`b13bb68c5c231ba51b73c63d2a0d7e73fa78a0a837d4e35b94a55ddf5006b3b3`.
Its `source-checkpoint.json` file SHA-256 is
`7d1f6858fa669af9de467c36c11e5aff0f3e7af99c0e65bbffcb2814c1040711`
and internal content hash is
`fef36fbcf2844f1da8510572a95c2f2978509bd2b021d2227c03c5ba5f3466f9`.
The checkpoint binds 706 source files, 159 directories, 572,044,578 retained
source bytes, and tree commitment
`dc95bb478bcb7fdb1b230fa4885402228c82f8614c80fe975a23510ec1922a48`.

The terminal request ledger is immutable evidence, not new authority:

- Massive: 363
- Alpaca: 28,831
- SEC: 1,328
- Total: 30,522
- Blocked attempts: 0

## Repair boundary

The sole v0.12 behavioral change is the explicit interpreter used for the
same-step environment comparison. A workflow regression test requires that
invocation to use `.venv-v12/bin/python` after the editable project install and
forbids the failed plain-Python form. The inherited v0.11 final-summarizer
repair still requires the full preflight to load every retained candidate and
float record and reproduce exactly:

- 30 dates;
- 946 candidates;
- 946 float records;
- 737 `composite_figi` identities; and
- 209 `unique_cik_fallback` identities.

The context manager temporarily replaces only
`historical_float_v04._candidate_identity` with the audited
`candidate_identity_v06`. No source values are changed. The legacy function is
restored after the final summarizer returns or raises.

Scanner snapshots are rebuilt only from the frozen canonical scanner inputs in
the checkpoint. There is no acquire phase, provider wrapper, provider hostname,
provider secret, consumption-tag write, account endpoint, order authority,
Databento route, transcript access, retrospective label access, or policy
promotion in v0.12.

## Durable execution order

1. Validate the frozen v0.12 authorization, permanent v0.10 and v0.11 failure
   audits, both parent authorizations/workflows, and exact artifact-metadata
   fixture without credentials.
2. On manual attempt 1 only, verify the exact authorization commit, tree,
   research branch, and byte-identical dispatcher installed on `main`.
3. Fetch artifact `9877181150` metadata exactly once and validate its ID, name,
   digest, size, parent run, head SHA, and unexpired state.
4. Download that exact checkpoint from run `33706372901` and deeply validate all
   706 source files, manifests, hashes, lineage files, and frozen ledgers using
   the unchanged v0.10 checkpoint validator.
5. Recreate the pinned CPython 3.12 environment, invoke that environment's
   interpreter explicitly in the same step, require identical third-party
   packages, and allow only the editable project line to move from the v0.10
   commit to the exact v0.12 authorization commit.
6. Rebuild all 30 scanner snapshots from the canonical inputs without
   credentials.
7. Preflight all 946 authoritative identities, run the final deep replay under
   the narrow compatibility context, restore the legacy validator, and upload
   the completed 767-file label-blind source bundle.

Pushes to the research branch run validation only. The final recovery remains
unarmed until the workflow is installed byte-for-byte on `main` and an exact
manual attempt-1 dispatch is separately authorized.
