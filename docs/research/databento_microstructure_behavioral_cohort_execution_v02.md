# Databento microstructure behavioral cohort execution v0.2

## Status

Registered and unarmed. This bundle authorizes no Databento request, quote,
download, byte, or spend. The future execution authorization file
`research/strategy/microstructure-behavioral-cohort-v0.2-execution.json` is
intentionally absent.

## Purpose

The consumed v0.1 attempt quoted all five frozen `XNAS.ITCH` MBO requests below
the registered aggregate ceilings, made one time-series request, and then
stopped safely with `record_payload_invalid` before any feature comparison was
retained. The pinned Databento 0.83 interface accepts `price_type="fixed"` and
does not accept the removed `pretty_px` keyword.

Version 0.2 binds that immutable safe failure and the sole compatibility
correction. It changes no opportunity, symbol, date, causal anchor, prospective
quantity, request order, feature, horizon, Fill/Cancel mechanic, comparison,
threshold, strategy rule, or broker action.

## Frozen execution surface

- Cohort: 10 opportunities, 7 symbol-dates, 5 trading dates, and 5,558 fixed
  prospective shares.
- Provider surface: exactly five date-grouped `XNAS.ITCH` `mbo` requests using
  `stype_in="raw_symbol"`.
- DataFrame conversion: exactly `map_symbols=True`, `pretty_ts=False`, and
  `price_type="fixed"`.
- Future aggregate preflight ceilings: `$0.25` and `225,000,000` bytes.
- Every request must be freshly quoted before the first download.
- One first GitHub Actions attempt only; no automatic retry and no partial
  cohort substitution.
- Raw records and feature values remain ephemeral and cannot enter the public
  repository or GitHub artifact.

## Future authority gate

A later execution requires a new canonical v0.2 authorization file as the sole
change in a direct child of the then-published branch head. That file must bind
this contract, the v0.1 safe-failure audit, the unchanged cohort and protocol,
the exact parent SHA, five requests, and both aggregate ceilings. The consumed
v0.1 authorization is invalid in the v0.2 namespace.

The workflow path filter listens only for that future v0.2 authorization file.
Publishing this registration therefore cannot contact Databento or consume
credit.

## Claim boundary

A later successful run would establish only that the frozen label-blind
comparison mechanics executed deterministically on this accepted-panel slice
under the registered compatibility correction. It would not establish
predictive value, a profitable threshold, Ross-equivalent discretion,
consolidated national Level 2 coverage, realistic fills, generalization, or
profitability. A later safe failure is evidence and cannot be hidden by changing
the cohort or execution mechanics.
