# Sealed historical source freeze recovery v0.11

## Status and purpose

Run `33706372901` dispatched v0.10 exactly once from `main`. Its `validate`,
`consume`, and `acquire` jobs succeeded. Acquisition completed all 30 canonical
scanner-source dates, uploaded the provider checkpoint, and froze the final
request ledger at 30,522 of 40,000 attempts with zero blocked attempts. The
separate credential-free `freeze` job then completed all 30 scanner snapshots
but failed while constructing the final deep-replay report.

The failure is another identity-validator scope mismatch. The scanner adapter
correctly scoped the authoritative v0.6 identity rule while it loaded and froze
scanner data, then restored the legacy `historical_float_v04` implementation.
The final `summarize_source_root_v04` call later reloaded the float root through
that legacy implementation, which accepts `composite_figi` and obsolete `cik`
but rejects the 209 correct `unique_cik_fallback` records. The 737 Composite
FIGI records and all 209 CIK fallbacks are otherwise valid. This is not a
provider-data, credential, request-budget, acquisition, or scanner-freeze
failure.

v0.11 is a provider-free final-freeze child. It recovers the exact v0.10
provider checkpoint, replays its 706 source files and frozen manifests, rebuilds
the 30 scanner snapshots from canonical inputs without credentials, preflights
all 946 candidate and float identities, and scopes the existing v0.6 identity
rule only around the final deep summarizer. It restores the legacy function in
`finally`, including after exceptions. It does not rewrite any identity or
float record.

## Exact parent

The parent is v0.10 run `33706372901`, attempt 1, authorization commit
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

The sole behavioral change is the final-summarizer loader scope. Before final
deep replay, v0.11 requires the inherited full preflight to load every retained
candidate and float record and reproduce exactly:

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
promotion in v0.11.

## Durable execution order

1. Validate the frozen v0.11 authorization, permanent v0.10 failure audit,
   workflow, and exact artifact-metadata fixture without credentials.
2. On manual attempt 1 only, verify the exact authorization commit, tree,
   research branch, and byte-identical dispatcher installed on `main`.
3. Fetch artifact `9877181150` metadata exactly once and validate its ID, name,
   digest, size, parent run, head SHA, and unexpired state.
4. Download that exact checkpoint from run `33706372901` and deeply validate all
   706 source files, manifests, hashes, lineage files, and frozen ledgers using
   the unchanged v0.10 checkpoint validator.
5. Recreate the pinned CPython 3.12 environment, require identical third-party
   packages, and allow only the editable project line to move from the v0.10
   commit to the exact v0.11 authorization commit.
6. Rebuild all 30 scanner snapshots from the canonical inputs without
   credentials.
7. Preflight all 946 authoritative identities, run the final deep replay under
   the narrow compatibility context, restore the legacy validator, and upload
   the completed 767-file label-blind source bundle.

Pushes to the research branch run validation only. The final recovery remains
unarmed until the workflow is installed byte-for-byte on `main` and an exact
manual attempt-1 dispatch is separately authorized.
