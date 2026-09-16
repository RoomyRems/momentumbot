# Full-membership scanner minute capture

This child of `51232cf6be74b3cea7a79d446a3c129d4dbe61f4` continues the
owner's September 15 authorization to finish scanner inputs and reach the
discretionary integration. The 30 dates, memberships, prior exclusions, Micro
policy and account alternatives remain frozen. No transcript or outcome data
enters this capture. Existing context-assessment, leadership, daily-chart and
theme components remain shadow-only.

All 165,694 previous closes are reused from the verified daily handoff. The
new source is split-adjusted SIP one-minute bars for every dated member from
04:00 through 10:00 New York time, in 690 batches of at most 250 symbols.
This is a complete ranking cross-section, not a candidate-only ranking.
Raw candidate price/volume and exact same-time RVOL remain separate inputs.

Alpaca's [historical bars specification](https://docs.alpaca.markets/us/reference/stockbars)
defines inclusive bounds, symbol-then-time order, a page-wide 10,000-row limit,
and `next_page_token` exhaustion. The collector follows that protocol, retaining
original bodies and every request/receipt. Twenty pages per root and 13,800
attempts are hard ceilings, with no retries, redirects or replacement symbols.
The inherited source store limits payloads to 1.5 GB and metadata to 80 MB,
reserving space for the final success or failure report. Capture time is capped
at 150 minutes; request starts are at least 350 ms apart.

Only the existing Alpaca credentials are used after same-code full CI and a
separate create-only consumption tag. No subscription, new data product or
metered purchase is added. Current entitlement/billing is not inferred from
successful tests. The registration expires September 22.

Minute timestamps remain bar-start timestamps. The inclusive 10:00 bar is
retained as source evidence; the frozen scanner's start-plus-one-minute rule
prevents its use at a 10:00 decision. The reader supplies split close frames and
the saved split previous closes without applying another split factor. Missing
minutes are not invented; a symbol becomes explicitly empty only after its
entire request root is exhausted successfully. HTTP errors fail collection and
never become empty-symbol exclusions.

The collector reuses the existing transport, credential-safe retention,
pacing, report schema and source gate. The old registered launchers remain
immutable; the new scanner lifecycle entry point handles subsequent scanner
source modules. The independent verifier streams the original archive through
the minute parser, checks every member and receipt, and reproduces the report.
The provider-free day reader then binds the original ZIP and exact dated root
union. It consumes an independently accepted proof; it does not claim that a
caller-created proof authenticates vendor origin.

Focused checks cover pagination, order, schema, clock boundaries/DST, empty
responses, failures without retry, credential gating, full dated membership,
original archive replay/tampering and scanner day projection. Initial local
fixture errors used the fake clock incorrectly; production code was unchanged
by that fixture correction. Final normal and optimized logs are retained in
`research/data-audits/early-pullback-scanner-minutes-v0.1/`.

After verified capture: use the saved daily acquisition superset to bound raw
candidate and RVOL work, bind point-in-time float and publication-timed news,
then reconstruct scanner/Micro sources. Feed the causal leadership/news/chart
packets into the existing discretionary shadow path. Rank capture alone is
not a completed scanner, a financial result, or policy promotion.

## Saved acquisition superset and remaining normalization check

Offline reuse of the original daily archive applies the frozen split-consistent
daily gain/range acquisition predicate to both existing profiles. The union is
4,018 ticker/date cases (1,424 distinct symbols), at most one 250-symbol batch
per date, versus 165,694 full-universe ticker/date cases. The sealed
`saved-daily-acquisition-superset.json.gz` retains each selected case's source
body hashes, prior split close, split target high, raw high/low and matching
profiles. All 30 dates and source-member lineage are retained. Its content seal
is `92c9616b3a9c88f24aece25d181e858faeb9b5c703e53e2b4695309f61cda4ac`.
These full-day values are acquisition-only and must never enter runtime
features, AI prompts, candidate priority or retrospective strategy tuning.

Before actual scanner reconstruction, verify share-basis agreement between
the saved daily capture and the newly acquired split minutes. Alpaca `asof`
anchors symbol mapping; it does not freeze adjustment factors against later
splits. Separate capture times therefore require a basis check. The new day
reader supplies source frames without asserting that this remaining comparison
has passed. Bundle the check with candidate daily/RVOL acquisition; preserve
the saved previous closes and lineage even if explicit rebasing is required.

The existing `context_assessment.py` explicitly names scanner v0.1 and its
fingerprint. Integrate scanner v0.3 through an additive context contract/adapter;
do not relabel v0.3 output as the old source or mutate historical shadow
experiments. Reuse the existing causal attention, catalyst, daily-chart and
theme builders, with absent evidence remaining explicit abstention. Discretion
can be exercised in shadow mode before final account performance evaluation;
trade/risk authority remains a separate decision.
