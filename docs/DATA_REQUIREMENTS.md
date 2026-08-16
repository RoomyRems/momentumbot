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

Provider adapters are intentionally deferred until the deterministic contracts/tests are stable. Secrets must never be printed to workflow logs or stored in snapshots.
