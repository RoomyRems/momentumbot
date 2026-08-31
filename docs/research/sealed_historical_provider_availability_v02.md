# Sealed historical provider availability repair v0.2

## Root cause

The v0.1 workflow used `secrets.ALPACA_API_KEY` and
`secrets.ALPACA_API_SECRET`. Those are not the validated main paper-account
credential names in this repository. The working routing was frozen previously in
commit `e7db059bf258b4d069c788d6293307737d4cea2e`:

- `secrets.ALPACA_MAIN_API_KEY` is exposed to the runtime as `ALPACA_API_KEY`.
- `secrets.ALPACA_MAIN_API_SECRET` is exposed as `ALPACA_API_SECRET`.

The v0.1 HTTP 401 therefore does not establish that the stored main credentials are
invalid. It establishes only that the incorrectly routed generic pair was rejected.
Run `33348067097` remains a permanent safe failure and will not be rerun or edited.

## Isolated repair

The v0.2 child authorizes one call: the identical Alpaca SIP `SPY` daily-bars request
used by v0.1. Its endpoint, parameters, selected dates, pagination rule, retained
summary, and `$0` incremental-cost declaration are unchanged. Only the GitHub Actions
secret mapping changes to the validated `ALPACA_MAIN_*` names.

The successful v0.1 Massive samples and Databento dataset-range result are inherited by
their frozen report hash. V0.2 cannot call Massive, Polygon, or Databento. It cannot
download a universe or intraday data, read an account endpoint, submit an order, open a
transcript value, retry itself, or rerun v0.1.

## Interpretation

A v0.2 pass would complete the provider-availability gate and permit registration of a
separate full-data acquisition and cost contract. It would not itself authorize data
acquisition, runtime execution, label review, policy promotion, paper orders, or live
orders. A v0.2 failure is preserved and closes this repair path without substitution.
