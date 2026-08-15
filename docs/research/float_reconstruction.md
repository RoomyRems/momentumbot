# Historical float reconstruction

Ross Cameron's scanner-style float is a share count. Historical vendors rarely expose a clean, point-in-time free-float series, so MomentumBot treats float as a sourced estimate with explicit causality and provenance rather than as an unqualified integer.

## Source hierarchy

1. **SEC EDGAR (production source):** free, official filings and XBRL facts.
2. **SEC-API.io `/float` (validation oracle):** commercial parser used sparingly to validate EDGAR extraction. The free key is finite and is not used in ordinary CI/backtests.
3. **FMP current float:** useful for current/paper cross-checking only; it is not a historical backtest source.

## SEC facts and units

Two different SEC concepts matter:

- `dei:EntityPublicFloat` is the aggregate **market value in USD** of voting/non-voting common equity held by non-affiliates, typically measured around the end of the issuer's second fiscal quarter and disclosed later in an annual report.
- `dei:EntityCommonStockSharesOutstanding` is a **share count**, usually disclosed on 10-K and 10-Q cover pages as of a more recent date.

MomentumBot never treats the dollar public-float value as though it were already a number of shares.

## Causal conversion

For a public-float disclosure:

```text
implied non-affiliate float shares
    = disclosed public-float USD
      / causal historical share price on the disclosure's measurement date
```

The resulting share count is explicitly labeled an estimate.

The disclosure is **not available to the strategy on its measurement date**. It becomes usable only after the filing was accepted by EDGAR. The `submissions` API provides acceptance timestamps for recent filings; when an exact timestamp is unavailable, MomentumBot delays availability conservatively rather than allowing same-day leakage.

## Conservative roll-forward

Annual public float can become stale after offerings, conversions, buybacks or other changes in shares outstanding. Between annual public-float observations, MomentumBot can roll the anchor forward using newer 10-Q/10-K shares-outstanding disclosures:

```text
affiliate shares at anchor
    = anchor outstanding - anchor implied float

rolled float
    = current outstanding - anchor affiliate shares
```

For the low-float qualification filter, the implementation does **not** reduce the float estimate after a buyback until a later public-float disclosure confirms that reduction. Net increases in shares outstanding therefore raise estimated float; decreases alone do not make a stock newly qualify. This deliberately prefers false rejection over falsely classifying a diluted stock as low-float.

This roll-forward still cannot observe every affiliate sale or intraperiod financing. Later research should add staleness limits and financing/corporate-action vetoes around uncertain estimates.

## Scaling to the full market

Direct `data.sec.gov` APIs require no authentication. For large historical builds, the SEC recommends its nightly bulk archives rather than thousands of individual API calls. MomentumBot should therefore use:

- `companyfacts.zip` for XBRL facts at scale;
- `submissions.zip` / per-CIK submission history for filing chronology and accession mapping;
- targeted `data.sec.gov` requests only for updates or gaps.

SEC fair-access rules currently limit automated users to no more than 10 requests per second and require an identifying User-Agent.

## SEC-API trial policy

The SEC-API.io free trial is 100 calls **total**, not a recurring monthly allowance. The repository's automatic provider-smoke workflow does not receive `SEC_API_D2V_KEY`; only a deliberate manual workflow dispatch can expose the key to the smoke script. Validation calls should be reserved for a stratified sample of low-float, reverse-split, multi-class and delisted issuers so we can quantify disagreement between our free EDGAR reconstruction and the commercial parser.
