# Databento microstructure feature coverage v0.1

## Purpose

This child extends the verified INTJ threshold-free feature replay to the three remaining mechanically selected engineering cases: EQPT, AMC, and GMM. It reuses the exact v0.3 per-instrument `F_LAST` repair and frozen feature engine. It does not change a feature, select a window or threshold, modify Micro-v0.1, or affect a broker or account.

The registration content SHA-256 is `0b098ea45120a1dd310dcf316c6ff31079ec1a5ca778bf078ca7698c03d6e18a`.

## Current status: unarmed

The execution file `research/strategy/databento-microstructure-feature-coverage-v0.1-execution.json` is intentionally absent. The workflow listens only for a future direct-child push containing that sole file. Publishing this bundle therefore cannot import the provider SDK, call Databento, or spend credit.

A later authorization must bind the exact published parent, permit one first GitHub Actions attempt, and retain these hard aggregate ceilings:

- exactly three MBO requests, in EQPT → AMC → GMM order;
- no more than `$0.08` quoted cost;
- no more than `80,000,000` quoted billable bytes;
- no retries, batch requests, live subscriptions, or MBP-10 redownloads.

## What a later run records

The runner downloads each file only into an ephemeral directory, reconstructs per-instrument events with the verified repair, and evaluates the unchanged one-, five-, and ten-second feature mechanics twice. The persisted report contains only non-reconstructable counts, availability totals, exact-replay booleans, aggregate quote totals, and cryptographic digests. It excludes raw records, prices, sizes, order IDs, feature values, labels, outcomes, credentials, exception messages, and temporary paths.

Metadata for all three requests must pass the fixed aggregate budget before the first download. After downloads begin, the runner stops on the first fixed safe failure and never retries. Every raw file is deleted before the report is finalized.

## Claim boundary

A three-case pass would show that the frozen mechanics replay across all four mechanically selected cases when combined with the verified INTJ result. It would still be engineering evidence only. It would not establish predictive value, a profitable threshold, Ross Cameron-equivalent discretion, consolidated national Level 2, realistic fills, or profitability.

## Files

- Registration: `research/strategy/databento-microstructure-feature-coverage-v0.1.json`
- Parent success: `research/data-audits/databento-microstructure-feature-diagnostic-v0.3-run-32483408413-success-2026-08-21.json`
- Runner mechanics: `src/momentumbot/research/databento_feature_coverage_v01.py`
- CLI: `scripts/run_databento_microstructure_feature_coverage_v01.py`
- Inert workflow: `.github/workflows/databento-microstructure-feature-coverage-v01.yml`
- Tests: `tests/test_databento_feature_coverage_v01.py`
