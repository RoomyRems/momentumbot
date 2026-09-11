# Fixed new-panel provider availability v0.1

This additive child of `0b13bc2af53f0b40b8e9128587abc78a89d48de1` implements
the previously registered four-request availability plan. The hypothesis is
limited: those exact requests can establish endpoint access, selected daily
date presence, two historical membership samples and relevant dataset/schema
range coverage. They cannot establish complete market-source provenance or
the hybrid strategy's profitability.

## Verified hosted result

[Run 34655893791](https://github.com/RoomyRems/momentumbot/actions/runs/34655893791)
completed successfully on push attempt 1. Its sole-file execution commit is
`fecb9744d23015387180fdfa3b60467392f57e72`, tree
`7a88f1cf43af00733400362ea9cbf6e544ce9836`, with tested code parent
`c9434f8417adfde22e564e513c4877d0bef99529`. Parent
[CI 34655360294](https://github.com/RoomyRems/momentumbot/actions/runs/34655360294)
ran 2,603 tests successfully, with the same 73 optional SDK skips and all 31
new tests passing. Every consumption and provider job step succeeded.

Exactly four attempts completed: one Alpaca, two Massive-family and one
Databento request. The Alpaca response had 56 daily records and all 30 selected
dates, with no missing selected dates or remaining page. Each membership
sample had one matching row and a remaining page, preserving its incomplete
universe scope. Dataset, `mbp-1` and `status` ranges all covered the interval.
No request was retried or replaced, and no strategy outcome was opened.

Both downloaded ZIPs match GitHub's independent artifact digests. All 14 result
files validate; the four common JSON files are byte-identical to the nine-file
consumption artifact. Its upload predates the first provider intent. The
permanent consumption ref still points to the exact execution commit. The
Python version and installed dependency versions match the frozen environment.

The [hosted verification](../../research/data-audits/early-pullback-provider-check-v0.1/hosted-verification.json)
and [sanitized report](../../research/data-audits/early-pullback-provider-check-v0.1/hosted-report.json)
are preserved with the original ZIPs. Report content hash:
`652617e5539103ad984243d00afb9297d4c794bf20fa31720788ced4c6056429`.
Verification content hash:
`f317d377651a217fe38c846fd8dbc47e4a07148dc90b2fcac91a903fa4919e06`.

The authorization is consumed. Limited availability is verified; full-session
hours, exhaustive membership/discovery, common source provenance and historical
execution remain separate gates. No paid capture or additional provider run
is activated by this success record.

## Frozen scope

The account checkpoint, all 30 selected March–May 2026 dates, both independent
account arms, scanner/Micro rules, first-two gate, risk, execution, management
and dated fee assumptions remain unchanged. The original losing baseline and
the user's waiver of another local historical baseline replay remain intact.
The prior plan and preparation records remain unarmed and immutable.

| Ordinal | Exact request | Retained projection |
|---|---|---|
| 0 | Alpaca SIP SPY daily bars, raw, March 3–May 21, as-of May 19, limit 1,000 | Counts, selected date presence, missing dates, pagination status |
| 1 | Massive historical active US-stock membership, March 4, limit 1 | Count, required-field/filter checks and pagination status |
| 2 | Same membership request for May 19 | Same bounded summary |
| 3 | Databento `metadata.get_dataset_range`, `XNAS.ITCH` | Dataset range and the `mbp-1`/`status` schema ranges |

The parameters and their hashes are copied exactly from the frozen plan.
There is no pagination, retry, redirect, endpoint substitution after failure,
intraday download, SEC/news request, broker/account request or order submission.
The two membership samples must remain visibly incomplete universe evidence.
SPY daily presence is not independent proof of full-session hours.

## Transport and evidence

The new transport uses standard-library HTTPS directly, without an SDK that
could retry. The existing hash-pinned provider-free Python environment is
retained. Alpaca uses the validated `ALPACA_MAIN_*` GitHub secret aliases.
The presence of a Massive key selects its route before transport; otherwise
the existing Polygon credential route is selected. That choice remains fixed
for both samples. Databento uses Basic authentication for the exact metadata
endpoint; its `method` field identifies the URL, not an additional query.

Every attempt has an fsynced intent before network access. Each response is
read at most to 262,144 bytes plus one oversize-detection byte. Raw bodies are
hashed and discarded. The receipt retains a status code, byte count, complete
or partial digest, fixed route, request identity, timestamps and the permitted
projection. It excludes provider error text, credential values, raw prices,
membership symbols, company names, pagination URLs and unapproved fields.

Failed requests consume their ordinal. The other distinct requests can still
produce evidence, but the failed request is never retried. An interruption
retains its intent without inventing a response. The final inventory marks
partial output incomplete. A completed probe has exactly 14 JSON files.
The verifier recomputes request, consumption, receipt, report and file bindings
against separately supplied execution and artifact identities. It opens the
already pinned ZIP bytes in memory rather than reopening an unverified path.

Discarding raw responses is intentional for this availability scope. Their
hashes bind the tested hosted transport to the response observations; they do
not allow an independent reconstruction of discarded provider rows. A later
market capture must retain its own complete, verifiable source provenance.

## Authorization and one-shot execution

The code registration itself authorizes zero provider calls. The user's
instruction to proceed with provider provenance and bounded capture authorizes
the next four-request availability execution, with no additional spending.
After the code passes the required local suite and hosted CI, a separate commit
may add only the exact execution JSON. It binds the code commit/tree, registration,
request manifest, workflow hash and successful parent CI run.

Only that sole-file addition on `phase-3-historical-snapshot`, as a first-attempt
push, can run the workflow. A job without provider credentials validates the
checkout, frozen files, focused adversarial tests and exact successful CI
receipt. It atomically creates `refs/tags/early-pullback-provider-check-v0.1-consumed`
and durably uploads its consumption evidence before the provider job begins.
The provider job has read-only repository permissions, rechecks the permanent
ref and matching receipt, and receives credentials only in its bounded probe
step. A duplicate run, changed file, parent mismatch, failed CI, missing receipt
or existing consumption ref stops access. No branch/tag force update, rerun or
deletion is part of the runner.

The incremental-spend ceiling remains $0.00; actual billing is not inspected
or claimed known. This uses the existing provider routes for minimal API and
metadata requests, without changing subscriptions or ordering paid datasets.
Paid historical capture remains disabled pending exact requests and quoted
per-request/aggregate ceilings.

## Verification and remaining work

The focused suite covers real request construction with a fake transport,
DST, missing dates, per-schema coverage, exclusive range ends, malformed JSON,
unapproved fields, response-byte limits, credential routing, failures,
interruption, repeat prevention, strict checkout/CI/consumption identity,
read-only provider-job permissions and independent artifact validation.
These fixtures are component tests and contain no evaluation-case outcomes.
All 31 focused tests pass normally and with assertions disabled under pandas 3.
The local full suite runs 2,603 tests in 350.979 seconds: 2,530 pass and 73
optional Databento SDK tests are skipped because that SDK is not installed in
this environment. All new transport tests run; this transport has no SDK
dependency. Compilation and undefined-global checks pass. Exact results are retained in the linked
[implementation verification](../../research/data-audits/early-pullback-provider-check-v0.1/implementation-verification.json).

The next capture stage needs independent full-session confirmation and the
complete causal source request graph: point-in-time membership/identity,
corporate actions, float/SEC/news, scanner cross-section, common SIP/minute
sources, and trigger-bound execution/management data. Availability success
does not open historical replay or financial evaluation. The full paired
account chains must be frozen before the registered comparison is opened.

Crucial discretionary/context components remain unintegrated. Transcripts
remain available for offline versioned design, with recap actions, fills,
later outcomes and evaluation narratives excluded from backtests and runtime.

## Endpoint references

Transport mapping was checked against the official
[Alpaca historical-bars reference](https://docs.alpaca.markets/us/reference/stockbars),
[Massive historical ticker reference](https://massive.com/docs/rest/stocks/tickers)
and [Databento Historical API reference](https://databento.com/docs/api-reference-historical/basics/authentication?historical=http&live=http).
The Databento response has an exclusive end and potentially narrower per-schema
ranges; the check requires both requested execution schemas to cover the panel.
