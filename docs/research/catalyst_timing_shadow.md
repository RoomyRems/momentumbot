# Catalyst timing shadow features

## Purpose

Ross's recaps show that news can turn a stock into the obvious focus, but DSY also shows that a no-news stock can be preferred when it matches the active theme. A simple `has news` flag therefore cannot represent his catalyst judgment.

`catalyst-timing-shadow-v0.1` adds only the causal chronology needed before any semantic interpretation: whether provider news was present at market qualification, when the first and latest provider events became available, whether event counts changed, and whether market qualification came before the first known event. It does not score quality, relevance, novelty, materiality, dilution risk or theme fit.

## Why this is separate from attention

Three clocks must not be collapsed into one:

1. the stock causally satisfies the market gate;
2. a provider event becomes available;
3. the stock becomes a market leader or attracts the trader's attention.

The extractor uses only events whose `published_at` is at or before the simulated decision time. Provider-relative absence remains distinct from a provider error and never means universal no-news.

## Frozen two-date validation

The extractor reproduced one row for every row in the successful frozen scanner artifact: 511 rows on 2025-04-03 and 1,702 rows on 2026-07-09. No future publication or retrospective trade label entered the derivation.

| Case | Causal chronology | Interpretation |
|---|---|---|
| TIVC, 2025-04-03 | First frozen provider event was published 5,543 seconds before the 11:00 UTC market qualification. | Provider news already existed when the candidate activated, but timing alone says nothing about its quality or Ross's decision. |
| VRAX, 2026-07-09 | Market qualification occurred at 11:32 UTC. The first frozen provider event was published at 11:34:33, entered the 11:35 decision row, and VRAX became the gain leader at 11:38. | Market motion preceded this provider event by 153 seconds, and leadership followed the event by 207 seconds. These are distinct causal states. |

Ross retrospectively described VRAX hitting his proprietary scanner about 15 seconds after news at roughly $3.41. The frozen reconstruction instead market-qualifies it at $5.25 before the Alpaca event. That discrepancy is preserved. It means our market gate and provider feed do not reproduce his discovery path; it is not a reason to rewrite either timestamp to match the recap.

Across the 21 candidates, 11 had provider news at activation and 10 had provider-relative no-news. GT, OSRH, HOUR and VRAX qualified before a later first provider event became available. This confirms that market qualification and provider news cannot be assumed to occur together.

## What remains missing

Provider timing does not establish causation or substance. The stored feed can contain multi-symbol or broadly syndicated stories, and a zero count says only that this provider returned nothing by that time. A faithful catalyst layer still needs causally available titles/articles/filings, issuer resolution, novelty and dilution checks, and evidence-backed theme comparison.

The earlier Micro activity cohort cannot supply that validation: it retains only two early qualifiers per date, omits the full news/rank context, and is concentrated at the 07:00 ET boundary. A broader panel must include every causally qualified candidate and freeze all provider inputs before any retrospective Ross comparison.

Until that panel exists, catalyst timing remains a research feature with no strategy, order or risk authority.
