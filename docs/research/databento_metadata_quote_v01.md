# Databento metadata quote v0.1

## Purpose

This child gate turns the frozen `level2-tape-feasibility-v0.1` plan into a
bounded provider check. It uses the repository secret `DATABENTO_API_KEY` only
to ask Databento whether the four registered symbol-dates are available and
what five exact schema requests would cost. It does not request a single market
data record.

The child contract content SHA-256 is
`1c9401e49d500c38715dd61c7f180e3eb868d71b9a28926caa4b399d335f45b1`.
Its immutable parent remains
`6d3a41d6bde3844900bc880632d8bc9d6c5f7b787edd5f0c302a709dcb9c1bf1`.

## Exact scope

The workflow checks `XNAS.ITCH` for `INTJ`, `EQPT`, and `GMM` on July 10,
2026, and `AMC` on July 20, 2026. For each case it quotes:

- MBO from 00:00 UTC through 10:10 New York time, so the later integrity gate
  can investigate a complete provider-day starting state;
- MBP-10 and trades from 06:50 through 10:10 New York time, padding the frozen
  06:55–10:05 strategy window;
- definition and status for the full UTC trading-date day.

All boundaries are exact multiples of ten minutes. The 20 individual quotes
are intentionally summed even though a later acquisition may not need every
redundant schema. That makes the result a conservative budget ceiling rather
than a favorable estimate.

## Cost guard

The user reported $125 in new-user credits. This first gate permits free
metadata queries only and freezes a $12.50 review ceiling—10% of the reported
credit—for the conservative four-case, five-schema sum. A quote above that
amount fails closed. A quote below it still does not download data; the quote
artifact explicitly has no acquisition authority.

The only callable surfaces are dataset/schema/field/unit-price metadata,
dataset range and condition, point-in-time symbology, billable size, and exact
cost. Time-series retrieval, batch jobs, batch downloads, and live
subscriptions are prohibited by the contract and absent from the workflow.

## Artifact and gate

The push-triggered workflow uses the pinned official Python client
`databento==0.83.0`, scopes the secret to one quote step, and uploads a
sanitized report whether the provider check passes or fails. The report keeps
metadata, resolution status, byte estimates, and dollar quotes. It never keeps
the key, returned instrument identifiers, or raw market data.

`G0` passes only if all of the following are true:

1. `XNAS.ITCH` is available for the requested range.
2. MBO, MBP-10, trades, definition, and status metadata are present.
3. All four raw symbols resolve point in time.
4. All 20 billable-size and cost results complete.
5. Their conservative sum is no more than $12.50.
6. No provider error or market-data endpoint call occurs.

A pass establishes availability and price only. Dataset integrity, complete
book initialization, normalization, reconstruction, feature mechanics,
execution value, and strategy value remain later gates. Nasdaq depth remains
single-venue data, not consolidated national Level 2.

## Reproduction

With `DATABENTO_API_KEY` set in the environment:

```bash
PYTHONPATH=src python scripts/quote_databento_microstructure.py \
  --output /tmp/databento-microstructure-metadata-quote-v0.1.json
```

Files:

- Contract: `research/strategy/databento-microstructure-metadata-quote-v0.1.json`
- Quote implementation: `src/momentumbot/research/databento_quote.py`
- CLI: `scripts/quote_databento_microstructure.py`
- Workflow: `.github/workflows/databento-microstructure-quote.yml`
- Tests: `tests/test_databento_quote.py`
