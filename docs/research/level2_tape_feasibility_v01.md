# Level 2 and tape feasibility v0.1

## Purpose

`level2-tape-feasibility-v0.1` is a bounded data-capability registration. It asks whether historical and eventually live order-book/tape data can be acquired, normalized, reconstructed, and replayed honestly before MomentumBot defines any Level 2-dependent trading rule.

It does not authorize a data purchase, broker change, paper order, live order, feature threshold, or policy promotion. Its content SHA-256 is `6d3a41d6bde3844900bc880632d8bc9d6c5f7b787edd5f0c302a709dcb9c1bf1`.

## Cohort boundary

The engineering cohort was derived from frozen ZIP `3b59e4b1a69e268158f6ccbead1fe9abae425fc249e72b34f466e53ebba56b20` before any provider download:

- retain every July symbol-date whose label-blind Micro-v0.1 replay recorded at least one fill;
- retain all 36 symbol-dates and 35 unique symbols;
- use no Ross action, recap, P&L, later price, or management result;
- sort by causal SIP trade-row count, date, and symbol;
- choose activity ranks 0, 11, 23, and 35 for a four-case mechanical smoke test.

The smoke cases are `INTJ` on July 10, `EQPT` on July 10, `AMC` on July 20, and `GMM` on July 10. They span 217 to 795,823 causal SIP trade rows. They may test access, storage, normalization, book reconstruction, and feature mechanics only. They cannot fit thresholds or support P&L claims.

Any later behavioral or economic evaluation belongs to the already-preregistered August 24–September 4 calendar and must use every symbol-date that produces at least one frozen Micro-v0.1 fill. The feature policy must be frozen before those results are opened.

## Data and broker separation

The two existing Alpaca paper accounts remain unchanged: main at $30,000 and small at $2,000. A market-data provider can feed the strategy while a separate broker adapter owns account and order operations.

Alpaca's documented equities streams expose IEX or SIP trades, quotes, bars, and related status messages. Those inputs are useful for consolidated tape and top-of-book work, but they do not constitute full multi-venue depth. See [Alpaca real-time stock data](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data) and [Alpaca market-data plans](https://docs.alpaca.markets/us/docs/about-market-data-api).

Databento is the first bounded historical depth candidate because it documents:

- `mbo` market-by-order/full-book events;
- `mbp-10` price-level depth;
- trade, definition, status, and snapshot conventions;
- common historical/live normalized schemas and replay.

See [Databento equities](https://databento.com/equities), [MBO schema](https://databento.com/docs/schemas-and-data-formats/mbo), [MBO snapshots](https://databento.com/docs/standards-and-conventions/mbo-snapshot), and [pricing](https://databento.com/pricing).

The first proposed dataset is Nasdaq TotalView-ITCH (`XNAS.ITCH`). It is explicitly one venue's depth, not a consolidated national Level 2 book. Multi-venue depth may later require additional venue feeds, but only after the bounded Nasdaq experiment demonstrates useful, reproducible information.

IBKR remains a possible future broker or live-depth candidate. Its API documents `reqMktDepth`, but its published error reference currently describes a maximum of three distinct market-depth requests. It is not the first historical research backbone. See [IBKR market depth](https://ibkrcampus.com/docs/tws-api/doc/market-data-live/market-depth-l-2/request-market-depth) and [IBKR API limits](https://ibkrcampus.com/docs/tws-api/ref/error-codes).

## Canonical event boundary

The provider-neutral code requires explicit provider, dataset, venue, point-in-time instrument identity, event and receive timestamps, sequence, action, side, price, size, order ID when available, and snapshot/data-quality flags.

It fails closed when:

- a book mutation appears before a clear or complete snapshot;
- live records arrive before snapshot completion;
- receive time precedes event time without a provider quality flag;
- non-snapshot channel sequence reverses or repeats;
- aggressor side is missing but not marked `unknown`;
- venue scope or point-in-time identity is ambiguous.

Symbol-filtered venue-global sequence gaps are recorded rather than called missing because filtering can legitimately omit messages for other instruments.

## Registered feature hypotheses

The first feature families are spread/depth, displayed depth imbalance, ask replenishment, signed trade velocity, level-sweep velocity, executed-volume/price-impact mismatch, cancellation pressure, breakout progress failure, and depth-constrained slippage.

Every numerical threshold remains `null`. Hidden-liquidity output is a proxy, not proof of a specific hidden order. Cancellation pressure cannot be labeled as intent or spoofing.

## Stop/go gates

1. **Cost and entitlement:** obtain an exact quote for the four cases inside a user-approved budget. No broad download.
2. **Schema and integrity:** confirm required fields, definitions, venue scope, timestamps, market status, and complete initial book state.
3. **Reconstruction:** require two byte-identical builds and full event-count/hash reconciliation.
4. **Feature mechanics:** calculate only causal features with explicit unavailable states and no fitted thresholds.
5. **Prospective policy:** freeze a separate feature policy before evaluating the prospective account panel.

Failure at any gate is preserved and stops the downstream work. SIP Level 1 is never silently substituted for missing depth.

## Current state

- Source cohort: verified.
- Canonical schema and fail-closed validator: implemented with synthetic tests.
- Databento account/API key: not configured.
- Exact cost quote: not obtained.
- Data purchased or downloaded: no.
- Provider adapter, book reconstruction, and features: not yet implemented.
- Alpaca accounts or secrets changed: no.

The next external gate is metadata-only availability and exact cost estimation for the four smoke cases. If access is approved later, the planned secret name is `DATABENTO_API_KEY`; the key must be stored in GitHub secrets and never pasted into chat or an artifact.

## Reproduction

```bash
PYTHONPATH=src python scripts/audit_microstructure_source_cohort.py \
  /path/to/discretion-heldout-micro-runtime-v0.1.zip
```

Files:

- Registration: `research/strategy/level2-tape-feasibility-v0.1.json`
- Canonical schema and validators: `src/momentumbot/research/microstructure_contract.py`
- Source-cohort inspector: `scripts/audit_microstructure_source_cohort.py`
- Tests: `tests/test_microstructure_contract.py`
- Audit: `research/data-audits/level2-tape-feasibility-v0.1-2026-08-19.json`
