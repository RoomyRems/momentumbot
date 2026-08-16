# Layer-1 historical data contract

The deterministic baseline is cheap compared with a Level-2 replay, but the *quality* of the data matters more than the number of indicators.

## Required for honest historical scanner reconstruction

1. **Point-in-time U.S. stock universe**, including symbols that later delisted, renamed, merged, or disappeared.
2. **Consolidated one-minute OHLCV**, preferably from 04:00-10:01 America/New_York. The strategy starts near 07:00, but pre-07:00 bars are needed for indicator warm-up and for stocks already moving before retail brokers broadly open premarket access.
3. **Previous regular-session close** for every symbol.
4. **At least 50 prior daily sessions of volume** for the current RVOL denominator; at least ~252 daily bars are preferable for daily-chart/200-MA research.
5. **Point-in-time float** with an as-of timestamp. Current float projected backward is unacceptable.
6. **Corporate actions and symbol mapping**, especially reverse splits.
7. **Publication-timed news/headlines**. A backtest may use only headlines published before the decision timestamp.
8. **Complete cross-section for ranking**. Top-gainer/obviousness rank is invalid if the snapshot contains only hand-picked winners.

## Universe completeness levels

`universe_complete=true` is reserved for a universe whose membership is known as of the simulated date. A present-day provider asset census does not meet that definition merely because it includes both active and inactive rows.

MomentumBot distinguishes:

1. **Point-in-time complete:** membership, symbol identity and exchange eligibility are reconstructed as of the simulated date. This is eligible for full-scanner walk-forward evaluation.
2. **Complete relative to a frozen asset census:** every security in one downloaded provider master is handled consistently, but historically absent/delisted names may still be missing. This is conditional diagnostic evidence only.
3. **Candidate/reference subset:** selected symbols only. This can validate feature or execution mechanics, never scanner selectivity.

Alpaca's [`/v2/assets`](https://docs.alpaca.markets/us/reference/get-v2-assets-1) endpoint is frozen with all statuses and a SHA-256 census fingerprint when it is used. The endpoint has no historical membership `asof` parameter. The historical-bars [`asof`](https://docs.alpaca.markets/us/reference/stockbars) parameter supports symbol-name mapping for the queried entity; it does not prove that the input symbol list was historically complete.

The sanitized FMP capability audit on 2026-08-16 found that the configured entitlement can read a delisted-company page with symbol, exchange, IPO and delisting dates, but its active-universe and symbol-change endpoints both return HTTP 402. That combination is not eligible for a reconstruction prototype. The result and workflow provenance are frozen in `research/data-audits/fmp-universe-capability-2026-08-16.json`.

Massive/Polygon's official [All Tickers](https://massive.com/docs/rest/stocks/tickers/all-tickers) contract is the next provider gate because it accepts a `date` and defines `active` relative to the queried date. Its free Stocks Basic history window is currently documented as two years, which covers the present seed/reference period. This documentation is not evidence of our entitlement or complete coverage: the repository first runs a sanitized two-date schema probe, then requires a fully paginated and independently reconciled census before setting `universe_complete=true`.

The live schema probe passed on 2026-08-16 for both 2025-04-03 and 2026-07-09. Its frozen result authorizes only a paginated census prototype; see `research/data-audits/massive-universe-capability-2026-08-16.json`. The free tier is officially limited to [five requests per minute](https://massive.com/knowledge-base/article/what-is-the-request-limit-for-massives-restful-apis), so the full-census workflow spaces page requests by 12.5 seconds and retains bounded retry/loop guards. A completed fetch remains non-promotable until its entire historical membership set has usable downstream market data and its identity/type/exchange coverage is reconciled.

The paginated prototype subsequently exhausted 12 pages and 11,276 security records for 2025-04-03, and 13 pages and 12,977 records for 2026-07-09. A second independent fetch reproduced both content and membership fingerprints exactly. All nonblank observed security-type codes are recognized by a separately frozen 24-row provider dictionary; two 2025 records still have no reported type. These results and workflow/artifact provenance are frozen in `research/data-audits/massive-historical-census-2026-08-16.json`. They establish a reproducible point-in-time membership candidate, not `universe_complete=true`; the workflow now audits raw and split-adjusted historical bar sufficiency for every unique ticker before any security-type translation is frozen.

That market-data audit accepted every ticker syntactically and found the required prior/target daily-bar basis for 96.38% of the unfiltered 2025 census and 96.77% of the unfiltered 2026 census. Preferred shares account for 359 of 408 failures in 2025 and 355 of 419 in 2026. As a descriptive check only, the provider's `CS` and `ADRC` families have 99.91% and 99.93% sufficiency respectively across the two dates. The result is frozen in `research/data-audits/massive-alpaca-market-coverage-2026-08-16.json`; it does not yet authorize treating those type codes as the strategy universe. Multi-identity ticker collisions, contradictory type/name metadata, and listings without both a prior and target trading session remain explicit fail-closed cases until a separately fingerprinted eligibility contract is implemented.

Cross-sectional inspection confirmed that `CS` and `ADRC` cannot be whitelisted directly: their names explicitly identify 62 preferred/debt instruments in the 2025 census and 95 preferred/debt/rights instruments in the 2026 census. A frozen label-blind metadata audit now catches those contradictions and quarantines another 13 and 12 unit or unresolved depositary-share structures. The separate `massive-common-equity-v0.1` acquisition contract then requires a recognized U.S. primary exchange, exactly one semantically accepted identity, and complete raw/split prior and target sessions. It makes one decision for every census ticker and emits 5,448 provisional candidates for 2025-04-03 and 5,577 for 2026-07-09. The live artifact exactly reproduced the local membership fingerprints; provenance is frozen in `research/data-audits/massive-provisional-universe-v0.1-2026-08-16.json`. This is complete only relative to the fetched census and remains `universe_complete=false` pending symbol continuity, corporate actions and full point-in-time feature construction.

The subsequent identity/corporate-action audit joined the two provisional sets by Composite FIGI, with a unique nonblank CIK allowed only when FIGI was missing and never to collapse two different nonblank FIGIs. It found 205 changed-ticker identities and tested every pair through Alpaca's historical-bars `asof` mapping at both snapshot dates. The provider bridged 203 pairs over the full 15-month interval, including all four observed symbol-reuse cases. The two exceptions (`NAYA`/`IVF` and `SAG`/`INEO`) were independently present in Alpaca's bulk name-change ledger with an effective process date of 2025-04-28. That date is outside both frozen 120-calendar-day feature windows, so neither missing full-gap alias affects the bars required by these snapshots. Bulk Alpaca corporate actions and Massive splits were also exhausted for both lookback windows. Six no-FIGI, non-unique-CIK tickers remain explicitly quarantined on each date; the identity-resolved counts are therefore 5,442 and 5,571. The result is frozen in `research/data-audits/massive-identity-corporate-actions-v0.1-2026-08-16.json`. This clears identity normalization only for the two declared snapshots after quarantine; it does not make the universe complete or authorize walk-forward/policy-promotion claims.

Conditional snapshots must declare `universe_complete=false`, `universe_complete_relative_to_asset_master=true`, and explicitly prohibit full-scanner walk-forward and policy-promotion claims. Loading one requires an intentional diagnostic override.

## News snapshot scope

For a single trading-day snapshot, `news.csv` should contain only events considered eligible for that active momentum session (for example news released after the prior regular close through the simulated morning). The exact freshness boundary is still a declared research translation; the backtester never searches old news on its own.

## Not required yet

Layer 1 does not require historical Level 2/order-book depth, tick-by-tick trades, or quotes. Those become necessary for hidden-seller absorption, tape velocity, spread dynamics and detailed halt-resumption execution.

## Existing credential names

The repository is designed to eventually consume the already-configured secret names without committing values:

- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`
- `ALPACA_PAPER_ENDPOINT`
- `FMP_API_KEY`
- `MARKETAUX_API_KEY`
- `MASSIVE_API_KEY` (preferred for the historical ticker-census probe)
- `POLYGON_API_KEY` (legacy-compatible fallback for the same provider)

Provider adapters are intentionally deferred until the deterministic contracts/tests are stable. Secrets must never be printed to workflow logs or stored in snapshots.
