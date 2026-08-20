# Historical account diagnostic v0.1

## What this answers

This diagnostic gives an immediate, reproducible view of how the frozen paper-account limits interact with the already-frozen July 10–23 scanner and Micro runtime. It does not replace or modify the prospective August 24–September 4 account study.

The source market/scanner artifact is `discretion-heldout-runtime-v0.1`, ZIP SHA-256 `850d9cfba27d7677904ccf147251b3ff914292102be0e3c62fec7bb47b6f73bb`. The source Micro artifact is `discretion-heldout-micro-runtime-v0.1`, ZIP SHA-256 `3b59e4b1a69e268158f6ccbead1fe9abae425fc249e72b34f466e53ebba56b20`. Both artifacts were label-blind and frozen before account composition. The account overlay itself was registered after those sources existed, so the result is explicitly retrospective and non-promotable.

## Method

For each of the ten sessions, the builder finds the exact causal scanner row at each Micro qualification timestamp and reapplies the unchanged `current-general-2026` or `current-small-account-2026` profile. Provider-timed news presence supplies only the existing `has_fresh_news` boolean; catalyst quality is not inferred. Profile-rejected records remain visible but their Micro plans and outcomes are not passed to the account ledger.

The unchanged `account-chronological-integration-v0.1` engine then orders plan, entry and exit events and applies the existing paper-safe envelope: 0.25% campaign risk, 1% daily loss, 50% position notional, one open position and no more than two entries per campaign. Each day is an independent fixed-balance scenario: $30,000 equity and buying power for main, and $2,000 for small. No real account identifier, credential or broker snapshot is used, and no profit, loss, position or buying power carries into the next date.

Both profiles are same-anchor overlap diagnostics. Every frozen candidate anchor is evaluated, but the diagnostic does not search later scanner rows and re-run Micro from a later account-qualified activation. It can therefore miss a stock that first becomes account-eligible after the frozen general market/Micro anchor. The historical universe is also not full-walk-forward eligible. The small result is narrower still because general-profile discovery can omit otherwise valid small-profile stocks priced from $1.50 through $1.99.

## Result

Across the frozen 119 candidate activations, 27 passed the main account profile and 6 passed the small account profile within the available overlap universe.

- Main accepted 10 modeled entries. Nine reached their modeled stops and one July 10 GMM position remained unresolved: 577 synthetic shares at $3.92, $2,261.84 open notional and $74.95 modeled open risk. Closed stop-only P&L summed to -$680.57, or -2.2686% of the fixed $30,000 denominator. Four sessions had a closed loss and six had no closed P&L.

- Small accepted 2 modeled entries. One reached its modeled stop and one July 10 GMM position remained unresolved: 38 synthetic shares at $3.92, $148.96 open notional and $4.94 modeled open risk. Closed stop-only P&L summed to -$5.33, or -0.2665% of the fixed $2,000 denominator. One session had a closed loss and nine had no closed P&L.

These percentages are not strategy returns. The frozen Micro source did not register a profit target or a discretionary favorable-exit rule. Across the full source it produced 80 stopped outcomes, 7 `filled_open` outcomes and 187 non-triggered plan outcomes, with no target-hit outcomes. The account result therefore measures entry scarcity, sizing, stop exposure and unresolved-position behavior; it cannot measure winners, expectancy, a compounded equity curve or profitability.

The frozen result manifest is `research/frozen/historical-account-diagnostic-v0.1/manifest.json`. Twenty per-account session artifacts retain the exact engine events and hashes; the permanent manifest hash is bound in the audit.

## Reproduction and next gate

With the two exact source ZIPs available locally, reproduce the result with:

```bash
PYTHONPATH=src python scripts/build_historical_account_diagnostic.py \
  --source-zip /path/to/discretion-heldout-runtime-v0.1.zip \
  --micro-zip /path/to/discretion-heldout-micro-runtime-v0.1.zip \
  --output research/frozen/historical-account-diagnostic-v0.1
```

The useful next development step is a separately preregistered exit/management sensitivity that adds a causal, deterministic favorable-exit model without changing Micro-v0.1 or treating this pilot as tuning evidence. The prospective August 24–September 4 account capture remains the clean validation path and continues independently.
