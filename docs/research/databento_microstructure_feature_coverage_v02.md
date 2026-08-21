# Databento AMC/GMM repaired feature coverage v0.2

## Purpose

This child freezes the smallest remaining label-blind engineering continuation after the verified INTJ and EQPT feature replays. It applies the published event-local Fill/Cancel repair and unchanged threshold-free feature engine to AMC and then GMM. It does not change a feature, select a window or threshold, modify Micro-v0.1, or affect a broker or account.

The registration content SHA-256 is `1218c98f80cbf7c535636ddd67842ed6ebc0a39628eaababfc44a7a0b822e213`.

## Frozen verified parents

- INTJ success audit: workflow run `32483408413`, content SHA-256 `093f65e4d62b125e370d972a5bd9ee3880b5439d72072dd3fd533e4774d18ebb`, 238 sampled snapshots, exact independent replay.
- EQPT repaired-feature success audit: workflow run `32520311940`, content SHA-256 `d87addf40a080d132799cb14daf8f6096b661d97369e7ebd9f8e216609cfffbb`, 1,346 matched Fill removals, 2,289 sampled snapshots, exact independent replay.
- Published checkpoint: commit `a8e683465ac680ea233414455f8da568e0e6656c`, tree `91119666d04f39663442a0cb133bc28238a6229a`.

The repair continues to prefer the existing exact five-field identity. Within each completed `(publisher_id, instrument_id)` event, remaining Fill markers pair with Cancels by `(order_id, side)`, and the matched Cancel payload supplies the canonical removal. Fill remains book-neutral, and any unmatched Fill stops safely.

## Current status: unarmed

The execution file `research/strategy/databento-microstructure-feature-coverage-v0.2-execution.json` is intentionally absent. The workflow listens only for a future direct-child push containing that sole file. Publishing this bundle cannot import the provider SDK, call Databento, or spend credit.

A later authorization must bind the exact published parent, permit one first GitHub Actions attempt, and retain these hard aggregate limits:

- exactly two MBO requests, in AMC → GMM order;
- no more than `$0.07` quoted cost;
- no more than `65,000,000` quoted billable bytes;
- no retries, batch requests, live subscriptions, or MBP-10 redownloads.

The historical three-case preflight minus the independently verified EQPT quote implies `$0.069315630197` and `62,022,576` billable bytes for AMC plus GMM. That is registration evidence only. Any future authorized attempt must freshly quote both exact requests and make zero time-series calls if either aggregate ceiling is exceeded.

## Exact request order

1. AMC: `XNAS.ITCH`, `mbo`, raw symbol, `2026-07-20T00:00:00Z` through `2026-07-20T14:10:00Z`.
2. GMM: `XNAS.ITCH`, `mbo`, raw symbol, `2026-07-10T00:00:00Z` through `2026-07-10T14:10:00Z`.

INTJ and EQPT are excluded only because their exact-replay audits are verified. No Ross action, transcript label, P&L, later price, or feature output selected the cases or order.

## What a later run records

The runner first quotes both exact requests. If the aggregate preflight passes, it downloads each file only into an ephemeral directory, reconstructs per-instrument events with the frozen repair, and evaluates the unchanged one-, five-, and ten-second feature mechanics twice. It stops at the first fixed safe failure and never retries.

The persisted report contains only non-reconstructable counts, availability totals, exact-replay booleans, quote totals, and cryptographic digests. It excludes raw records, prices, sizes, order and instrument IDs, feature values, labels, outcomes, credentials, provider messages, and temporary paths. Each raw file is deleted before the report is finalized.

## Claim boundary

A two-case pass, combined with the frozen INTJ and EQPT audits, would establish deterministic engineering coverage across the four mechanically selected cases. It would not establish predictive value, a profitable threshold, Ross Cameron-equivalent discretion, consolidated national Level 2, realistic fills, execution quality, or profitability.

## Files

- Registration: `research/strategy/databento-microstructure-feature-coverage-v0.2.json`
- INTJ parent: `research/data-audits/databento-microstructure-feature-diagnostic-v0.3-run-32483408413-success-2026-08-21.json`
- EQPT parent: `research/data-audits/databento-microstructure-fill-cancel-repaired-feature-v0.1-run-32520311940-success-2026-08-21.json`
- Repair: `research/strategy/databento-microstructure-fill-cancel-repair-v0.1.json`
- Runner mechanics: `src/momentumbot/research/databento_feature_coverage_v02.py`
- CLI: `scripts/run_databento_microstructure_feature_coverage_v02.py`
- Inert workflow: `.github/workflows/databento-microstructure-feature-coverage-v02.yml`
- Tests: `tests/test_databento_feature_coverage_v02.py`
