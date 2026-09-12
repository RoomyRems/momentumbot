# Early-pullback capture plan v0.1

## Frozen parent and narrow result

This additive child starts from `cc59ca3f98861e98ae5b81335e76c10e5d2cca87`,
tree `4fd733ee57664651ce61519562d0f97862660ff6`. Its hypothesis is limited to
calendar and acquisition-planning mechanics: official schedules and a bounded
census request chain can prepare the fixed panel without changing policy,
granting acquisition authority or manufacturing source completeness.

The parent checkpoint's CI `34656355058` and walk-forward validation
`34656355064` both succeeded. The four-call availability operation remains
permanently consumed. No provider API, brokerage endpoint, transcript record,
new-panel price, strategy outcome or financial comparison was accessed here.
Public calendar and endpoint documentation were read separately.

## Scheduled full sessions confirmed, realized coverage still separate

On 2026-09-12, the official [NYSE calendar and hours](https://www.nyse.com/trade/hours-calendars)
and [Nasdaq calendar and hours](https://www.nasdaq.com/market-activity/stock-market-holiday-schedule)
were checked. Both list the same 2026 holiday and early-close dates and regular
equity hours. None of the 30 frozen March–May dates is a weekend, scheduled
holiday or scheduled early close. Every selected session is scheduled for
09:30–16:00 New York, 390 minutes. The first three dates open at 14:30 UTC;
the remaining 27 open at 13:30 UTC following the March daylight-saving change.

The [calendar observation](../../research/data-audits/early-pullback-capture-plan-v0.1/official-calendar-observation.json)
preserves the source URLs, observed date, factual schedule projection and its
limitations. This is a manually checked transcription, not an independently
downloaded raw HTTP archive. Its local hash commits the transcription only.
It does not prove realized uninterrupted sessions, absence of security halts,
or a captured historical provider calendar. Earlier artifacts' false calendar
authentication flags remain untouched. A source discrepancy must block capture
or reconstruction; it cannot cause a replacement date.

## Exact first-stage requests and proposed bounds

The [capture plan](../../research/data-audits/early-pullback-capture-plan-v0.1/capture-plan.json)
contains 31 exact initial GET envelopes on `api.massive.com`:

- One current ticker-type dictionary, `asset_class=stocks`, `locale=us`.
- One historical census first page for each of the exact 30 selected dates:
  `market=stocks`, `locale=us`, `active=true`, `date=<selected date>`,
  `order=asc`, `sort=ticker`, `limit=1000`.

Massive documents the [dated ticker query and pagination](https://massive.com/docs/rest/stocks/tickers/all-tickers)
and the [type dictionary](https://massive.com/docs/rest/stocks/tickers/ticker-types).
The dictionary is present-day taxonomy, not point-in-time membership evidence.
There is no current Alpaca asset-master reconciliation or hand-selected ticker
list. Security identity, duplicate membership, ordering and historical mapping
still require a complete capture verifier.

The inherited census operational limits propose at most 20 pages per date,
1,000 records per page, one type call, and a minimum 12.5-second request interval.
Thus **601 is a maximum HTTP-attempt budget, not an observed or expected count**.
Response and normalized-retention proposals are 16,000,000 and 1,500,000,000
bytes. Retries, redirects and runtime provider fallback are disallowed.
These are an unarmed specification, not an implemented network/retention guard.

The pure page planner binds each cursor request to the exact date/root query,
page ordinal and previous response hash. It rejects changed origin/path,
embedded credentials, extra or changed filters, duplicate parameters, invalid
cursors, cursor cycles, altered request chains and non-integer counts. A
terminal twentieth page can complete; a required twenty-first page fails
instead of declaring a truncated census complete. An empty exhausted census
is unavailable, not a zero-opportunity day. An empty page with a cursor is not
exhausted. Pages after exhaustion are rejected.

Caller-supplied page summaries and hashes are **not authenticated provider
evidence**. This helper has no transport, durable attempt ledger, origin proof,
row parser or historical activation mode. Failed/partial requests must remain
explicit in the future runner, never disguised as successful pages. A changed
or cancelled operation will need a separate preserved recovery decision.

## Complete dependency inventory, not complete request materialization

The plan records all 14 dependency nodes and their frozen mechanics references.
The following unresolved dependencies prevent a complete HTTP/cost inventory:

| Layer | Required evidence before exact downstream requests |
|---|---|
| Historical universe | Exhausted census pages and preserved PIT security identities |
| Identity / corporate actions | Historical symbol/share-unit continuity and original normalization inputs |
| Discovery / enrichment / scanner | Complete cross-section, frozen profile union, exact RVOL, causal SEC/news lineage and reconstructed activations |
| Micro sources / reconstruction | Common SIP/minute/warmup union, verified source reuse, all original causal triggers before the first-two gate |
| Entry / management / exit inputs | Trigger-bound nanosecond quote/status requests, original management windows and the complete shared exit-input union |
| Paid quote / capture | Independently verified exact-request quotes, finite per-request and aggregate hard ceilings, separately consumed capture authority |
| Paired accounts | Authenticated common sources and complete independent close chains for all 24 paths / 720 slots |

All dynamic request counts, the complete-capture request ceiling, actual costs,
paid per-request ceilings and paid aggregate ceiling remain explicitly unknown.
Unknown is not zero or permission to spend. Current authority is zero provider
calls and USD 0.00 incremental spend. Registration cannot lift those limits.

Next is a separate bounded census transport with tested complete-byte,
identity and exhaustion verification, then its exact-parent durable one-shot
execution record. Any capture must first establish applicable existing
subscription entitlement and zero incremental spend; paid sources need their
own exact quote/ceiling gate. The old four-call authorization cannot be reused.

## Reproducible verification and interpretation

```bash
PYTHONPATH=src:scripts python scripts/build_early_pullback_capture_plan_v01.py
PYTHONPATH=src:scripts python -m unittest tests.test_early_pullback_capture_plan_v01 -v
```

The command installs the existing network/subprocess audit guard before loading
the component. It reconstructs the full registration and saved plan and checks
the frozen availability ancestry. The explicit local `--freeze` mode writes
new files once; it cannot overwrite registered outputs or execute capture.

The 22 focused tests cover all dates, DST, rehashed calendar changes, complete
dependency retention, exact census roots, page-chain tampering, cursor safety,
both sides of the page ceiling, empty/unavailable distinctions, absence of
authority and the actual normal/optimized CLI including overwrite rejection.
Measured focused, optimized and full-suite outcomes are recorded in
[implementation verification](../../research/data-audits/early-pullback-capture-plan-v0.1/implementation-verification.json).

The completed pandas 3.0.5/NumPy 2.5.3 full suite ran 2,625 tests in 348.363
seconds: 2,552 passed, 73 optional SDK tests skipped, zero failures/errors.
All 22 new tests executed. Focused normal verification passed 22 tests in
4.128 seconds; optimized pandas 3 passed 22 in 3.388 seconds, both with no
skips. Compilation of `src`, `tests` and `scripts` and the diff check passed.
Registration: `a8111ed4eb7a64c76dbeceae51f580680c0e0ecce627402e89db10b94a452ff1`
(353 bound files). Plan: `e5ec94c657037d3e2f689b22d673895254cf55a449ea948dbd9c3eb8e0278596`.
Verification: `adec4df7e85b0576ce380f67958b89ec4bcfa5b3558737a5c5e0d7d2bf353961`.

The first standard full-suite process returned exit code 0, but its retained
log stopped during ancestry validation and contained no terminal test summary.
It is preserved as an **unverified attempt**, not a pass. No assertion failure
was reported, and the missing-log cause is unresolved. The first dedicated-stream
diagnostic runner then failed with 82 test-module import errors: running its
script from scratch omitted the repository root from Python's import path,
discovering only 1,637 tests. Its script, log, stack diagnostic and completion
record are preserved in the linked verification evidence. This was a runner
failure, not a passing subset. The corrected runner explicitly includes the
repository root, requires the exact 2,625-test inventory with no import errors
before starting, and writes a separate discovered/run/failure/error/skip receipt.
That corrected pandas 2.2.3/NumPy 2.3.5 process subsequently exited with code
139 during an existing source-adapter test, without a terminal receipt. Its
runner/log/stack archive is also preserved as failed verification. The cause
has not been isolated. The final bounded check uses the already available
pandas 3.0.5/NumPy 2.5.3 environment and removes the timed stack-diagnostic hook;
those operational changes do not establish which caused the earlier crash.
The test inventory and all product/ancestor code stay unchanged. No check,
strategy rule or data guard is bypassed. Hosted CI is checked independently
after publication; the earlier runtime failures remain visible regardless of
its result.

No frozen strategy/account mechanics or old-date validators changed. The user's
waiver of another local historical baseline replay stands; unit verification is
not that replay. The losing parent remains preserved. Crucial discretionary
and context integration remains outstanding, so component results do not settle
the full hybrid's edge or promise eventual profitability. Transcripts remain
offline, versioned design material, never evaluation-case tuning inputs.
