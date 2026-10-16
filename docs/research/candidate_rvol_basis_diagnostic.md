# Withheld RVOL histories: price/share-basis diagnostic

Implementation: `3cc1ba86d1e0480c468b741e706972dfd843b0c8`.
Parent: [exact source integration](candidate_rvol_exact_source.md), unchanged.

## Observed result

The [offline diagnostic](../../scripts/audit_candidate_rvol_basis.py) selects
all and only the sealed parent's withheld cases. It revalidates the original
source pages and compares all fifty prior sessions of each case, using exact
decimal arithmetic for 04:00–09:59 ET bars. No outcome/label selection occurs.

| Target / symbol | Prior sessions | Sessions with price and volume differences | Affected 15-minute buckets | Trade-count / presence differences |
|---|---:|---:|---:|---:|
| 2026-03-25 / MGN | 50 | 48 | 193 | 0 / 0 |
| 2026-05-19 / RUBI | 50 | 50 | 663 | 0 / 0 |

MGN has two exhausted empty sessions. Across both cases the audit compares
3,099 minute bars with 856 coarse bars. All original volume discrepancies are
reproduced exactly; every affected bucket also has OHLC differences. This
rules out a volume-only discrepancy in these observed comparisons, but does
not identify the provider's root cause or establish a safe adjustment factor.

For example, MGN's January 12 10:30 UTC bucket has coarse open/volume 78/35
versus minute-rollup open/volume 58.5/47; both count three trades. RUBI's March 9
08:00 UTC bucket has coarse open/volume 250/62 versus minute-rollup open/volume
1/16609; both count 73 trades. These are diagnostic observations, not scale
estimates to apply. Aggregated OHLC differences need not always indicate a
corporate action; the comparison does not promise vendor timeframe equivalence.

The exact histories were captured September 19; coarse histories September 17.
Their feed, adjustment, identity date, membership and aligned windows agree.
The parent's matching target mornings use earlier saved target minutes, not
a same-vintage target refresh for these two cases. Target agreement therefore
does not resolve the historical numerator/denominator basis.

## Parameter semantics and limits

Alpaca's [historical bars reference](https://docs.alpaca.markets/us/reference/stockbars),
checked October 16, 2026, describes `asof` as symbol/entity mapping across name
changes. `adjustment=split` adjusts prices and volumes for splits. The `asof`
parameter is not evidence of an adjustment cutoff or of a common data vintage.
This is reference documentation consulted offline, not an input to replay.

No authoritative mapping from the two captured adjustment vintages is present
in this comparison. Matching trade counts and price-scale differences are
consistent with a basis change, but cannot distinguish a corrected adjustment,
different provider processing, or another upstream issue. Neither archive is
declared correct merely because it is newer. No multiplier or tolerance is fit.

## Acceptance boundary and next work

Both cases remain withheld. No curves, raw execution inputs, ranking prices,
frozen exclusions or prior reports are changed. The 2,101 previously ready RVOL
cases remain component-ready, not full-scanner-ready. All correction, scanner,
replay, policy and trading authorization flags remain false.

Next, audit saved daily/raw/split source basis across the candidate population
with the same no-fit rule, preserving unavailable cases. Before repairing these
two RVOL cases, obtain independently attributable evidence tying history and
target to a common price/share basis. If that requires fresh data, prepare a new
bounded registration and obtain fresh acquisition authority; do not rerun the
consumed captures. Then complete historical float/news and the real scanner
adapter before discretionary shadow integration.

Evidence and reproducible command: [audit README](../../research/data-audits/early-pullback-candidate-rvol-basis-diagnostic-v0.1/README.md).
