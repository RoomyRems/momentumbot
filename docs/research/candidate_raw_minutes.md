# Bounded candidate raw-minute capture

Parent `73e91a22cd913469c50ce61e9bd14d4b554478cb` passed full CI
`35108918709` on September 16. The accepted full-membership split-minute
source remains unchanged. This additive stage captures raw candidate prices
and volumes for the same 30 evaluation dates.

The immutable saved daily acquisition superset has 4,018 symbol/date cases.
Only their symbols enter the new 30 batched requests. Full-day highs, lows,
profile matches and subsequent outcomes are not runtime inputs or priority
signals. Every symbol must belong to its original dated membership. No date,
threshold, strategy, account seed, identity mapping or risk rule changes.

Requests use existing Alpaca SIP access, raw 1Min bars, dated `asof` mapping,
04:00 through 10:00 ET inclusive, at most 250 symbols per batch and 10,000 bars
per page. Each root allows at most 20 pages: 600 attempts total, no retries
or redirects. The existing byte, pacing and duration ceilings apply. A bar
stamped 10:00 remains unavailable until 10:01. Empty members require a fully
exhausted successful response; errors never become empty results.

The new workflow reuses the shared hosted lifecycle: exact new child commit,
one successful same-code CI run, permanent create-only consumption, then
credential loading. It automatically verifies the original capture ZIP by
replaying every page and comparing reports, byte hashes and receipts. The
shared archive verifier is extracted additively; frozen parent files and
registrations are unchanged. Per-symbol ordering uses the accepted repair.

Eight focused tests pass normally and with assertions disabled; compilation
passes. They cover DST and symbol-only selection, exact saved population,
per-symbol order, original archive replay and tampering, failed HTTP retention,
request ceilings, credential gating and the hosted CLI. Initial development
failures are retained in the audit directory. Publication triggers full CI
and the gated capture; these local tests do not claim a hosted result.

Raw prices and volumes cannot substitute for split ranking or exact split
RVOL history. The capture enables paired raw/split source comparisons but
alone does not establish agreement between the older daily and minute
adjustment vintages. `asof` specifies symbol mapping, not a pinned adjustment
vintage. The complete rank population still needs basis verification; exact
50-session same-time RVOL, point-in-time float and publication-timed news
remain separate dependencies. No scanner, account evaluation, discretionary
order authority or live trading is enabled by this stage.
