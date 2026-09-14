# Frozen daily-coverage replay

Additive child of `8387c43e9fe899b2e1f1951b0127afa62aee46ca`. The hypothesis
is that exhausted raw daily pages can populate the existing dated coverage
adapter without treating partial or failed requests as missing securities.
No transcript, outcome, strategy threshold, risk rule or account replay changed.

`daily_coverage.py` admits the exact previously published reference panel by
compressed byte length, SHA-256 and content seal. Daily request roots come from
the unchanged bridge: 1,380 roots across 30 dates, raw/split SIP, target-date
`asof`, 250-symbol batches and the inherited 14-day window. Each root permits
at most ten pages and each response at most 16 MiB. This establishes a daily
protocol ceiling of 13,800 attempts; it is not a launch or spending authorization.

Pages must be complete, uncompressed HTTP 200 responses with strict JSON,
requested symbols, finite nonnegative bar values, coherent OHLC, aware
timestamps, ordered unique bars and no future session. Session observations use
New York dates. JSON mapping key order is ignored; symbol/time order and unique
daily sessions are enforced across pages. Cursors must advance, nonterminal pages
must contain data, and a remaining cursor at the ceiling fails closed.

No root result exists until pagination exhausts. No daily coverage result exists
until every raw and split root exhausts. Missing symbols in successful exhausted
responses become absent observations, not inferred invalid symbols. HTTP 400,
authentication, permission, rate-limit, transport and payload failures permanently
close that in-memory replay instance. They do not trigger retries or symbol removal.
The existing bridge receives its exact date/reference-bound six-boolean records;
all historical scanner, identity, financial and order gates remain closed.

The registration also records 60 **unarmed initial identity requests**: Alpaca
corporate actions and Massive stock splits for each target's preceding 120 calendar
days. Types and parameters match the existing identity audit. These sources still
need their own bounded pagination, raw retention and identity resolution. Current
corporate-action responses do not prove what was known at the historical time.

Provider contracts checked against [Alpaca historical bars](https://docs.alpaca.markets/us/reference/stockbars)
(symbol-first pagination, inclusive endpoints, date-specific symbol mapping) and
[Alpaca corporate actions](https://docs.alpaca.markets/us/reference/corporateactions-1)
(complete-data semantics and availability-delay warning). These sources inform
transport interpretation, not policy changes or performance claims.

## Verification and use

29 new tests cover positive two-adjustment pagination through the existing bridge,
empty versus incomplete evidence, date/reference scope, cursor/order/byte/page
bounds, HTTP failures, invalid numerics, duplicate JSON, New York session dates,
raw/split disagreement and the exact saved 1,380-root panel. Focused checks include
the 30 existing bridge tests, normally and with assertions disabled.

```bash
PYTHONPATH=src python scripts/replay_daily_coverage.py validate
PYTHONPATH=src python scripts/replay_daily_coverage.py replay \
  --date 2026-03-04 --input /absolute/path/to/events.jsonl \
  --output /absolute/path/to/fresh-result.json
```

The offline CLI accepts ordered `{request,response}` events; response has
`status`, `body_utf8`, `complete`, `encoding`. It reconstructs body bytes and
replays every event, rejecting extras, omissions and trailing events. It cannot
authenticate provider origin from a caller's file. It never reads credentials
or makes requests, and does not emit a partial result after failure.

Next: wire bounded transport and retained raw-byte artifacts, implement the
corporate-action page validators, and run through the existing exact-code-CI,
durable single-use hosted capture and independent archive verification safeguards.
No new provider request or charge occurred in this implementation. Do not reuse
the consumed census launcher. Discretionary/context integration remains unfinished.
