# Historical execution-input metadata quote v0.1

This metadata-only child binds the frozen execution/status plan at commit
`3af740c7ed80d04ba604399fa26b9d369d246271`, tree
`c91806b2929c714036dba3fc724ec790b627eca9`. It tests whether all 90 exact
`XNAS.ITCH` requests for the 109 historical Micro decisions have complete
nonzero size quotes and valid cost quotes. Zero size or an incomplete response
is an unavailable dependency, never a zero-trigger result.

The exact plan inventory is
`6aa9208ce5d37998021dcf09f30fb68ca3e5184b4505ea25c42f3f80b8ab38c1`;
the request-list content hash is
`4515172de55e48d42f1312b5b298dd2c126fccea700b39417cf600221d76e8ce`.
Validation re-derives that plan from every frozen Micro bundle member and
retains all 30 dates, 45 symbol/date pairs and profile-union identities. The
source Snapshot, original ledger, completed captures and runtime stay immutable.

## One consumed metadata operation

The code push runs provider-free validation only. After exact-parent CI and
dedicated validation succeed, a sole added
`research/strategy/sealed-historical-execution-input-quote-v0.1-execution.json`
records their run IDs, full code commit/tree, contract hash and workflow hash.
Only its first push attempt on the research branch can enter the quote job.
The existing user authorization covers this operational step.

Before any provider access, the workflow atomically creates
`refs/tags/sealed-historical-execution-input-quote-v0.1-consumed` and durably
uploads its exact consumption artifact. An existing ref fails closed. The
workflow has no manual dispatch entrypoint and never changes the installed
main dispatcher. A consumed operation cannot be rerun or repaired in place.

CPython 3.12.14 and `requirements-sealed-execution-quote-v01.txt` pin the hosted
environment. The lock preserves every original source dependency and adds
exact wheel hashes for Databento 0.83.0 and its dependencies. Normal/optimized
validation uses the actual pinned SDK with a fake HTTP transport; ordinary
CI also runs the full repository suite.

The sole provider step calls `get_billable_size` and `get_cost` once for each
frozen request, in order. Its transport permits only the 180 exact metadata
POSTs, including symbol, schema, feed dataset, and nanosecond start/end. It
rejects all other endpoints or parameters before network access. Each attempt
is journaled before transmission. Redirects and automatic retries are disabled;
responses are capped at 64 KiB, with 30-second connection/read timeouts.
The session does not use implicit environment proxies or netrc credentials.

Provider bodies and exception text are discarded. Separate metadata and HTTP
ledgers retain only exact request identities, typed numeric results, fixed
sanitized errors and HTTP status. The terminal report reconstructs every row
and total from those calls. It can pass only with all 90 complete nonzero-size
requests, 180 HTTP attempts, and no blocked attempts. An incomplete quote has
unknown aggregate totals; partial evidence is still uploaded.

## Retained evidence and next gate

The consumption artifact contains the ref receipt, sealed marker, execution
record, contract, lock, installed package freeze, and exact code-validation run
metadata. The result artifact contains the same marker/record/contract, frozen
request manifest, separate ledgers, terminal report and complete file inventory.
Independent verification must measure both ZIP digests, all members and JSON
content hashes, exact request order, numbers, and provenance before accepting
the quote gate. Green job status alone is insufficient.

This operation acquires no time series and authorizes no provider spend. A
successful verified quote is a prerequisite to a separately registered,
bounded acquisition with its own one-shot consumption record. There is no
account/fill simulation, order access, backtest, policy change, or retrospective
input in this stage. Missing execution/status or registered management inputs
remain blockers to downstream simulation.

Provider-free validation:

```bash
PYTHONPATH=src:scripts python scripts/quote_sealed_historical_execution_inputs_v01.py --validate-only
python -m unittest tests.test_sealed_historical_execution_quote_v01 tests.test_sealed_historical_execution_inputs_v01 tests.test_prospective_market_input_quote -v
```
