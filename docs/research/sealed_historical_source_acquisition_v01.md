# Sealed historical source acquisition v0.1

This is the first bulk-data child of the sealed 30-session walk-forward. It is
registered only after the provider-availability repair passed. It changes no strategy,
date, account, execution, or management rule.

## Exact scope

The workflow acquires and freezes, in order:

1. Fully paginated Massive point-in-time ticker membership for the 30 selected dates.
2. Alpaca SIP raw/split daily coverage and causal premarket market discovery.
3. First/last-date identity and corporate-action normalization, with the frozen
   identity rule applied independently to every intermediate date.
4. Point-in-time SEC float evidence and publication-timed Alpaca news for the resulting
   market candidates.
5. The causal scanner snapshots and deterministic gzip sidecars containing the exact
   canonical scanner inputs needed for provider-independent feature replay.

The present-day Alpaca asset master is deliberately skipped. Databento execution data
is not acquired in this stage; it remains candidate-bound and separately quoted.

## Hard budgets

- One workflow attempt; the authorization is consumed before provider access.
- 20,000 total HTTP attempts, including retries, enforced by one shared counter across
  every script process.
- 20 Massive census pages per date at 1,000 rows per page.
- At most 50 market candidates per date before SEC, news, or scanner continuation.
- At most three SEC attempts per endpoint and ten Alpaca news pages per symbol batch.
- 1.5 GB maximum retained normalized/canonical source tree.
- `$0` incremental provider cost and zero Databento calls.

The request counter persists only totals by hostname. It never persists a URL, query,
header, credential, symbol, or provider response. Bars and corporate actions also have
per-request pagination limits.

## Failure behavior

Any missing date, incomplete pagination, provider error, candidate-count breach,
request-budget breach, retained-byte breach, lineage mismatch, or incomplete source
gate fails the run. Dates are not replaced and failures are not converted to zero
opportunities. No automatic rerun or provider substitution is allowed.

Transcript values, Ross labels, actions, fills, skips, outcomes, account endpoints,
orders, and policy promotion remain prohibited. Successful source acquisition only
permits the next label-blind stage: freezing scanner/Micro decisions and registering a
separate candidate-bound execution-data quote.
