# Attention and leadership shadow features

## Purpose

Ross's DSY and VRAX recaps make clear that a chart pattern is not the whole decision. He also describes which stock is becoming obvious, where attention is leaving another leader, whether a move is on the day's theme, and whether a candidate has become the market's leading gainer.

`attention-leadership-shadow-v0.1` is a deliberately narrow step toward representing that context. It derives observable leadership features from the already-frozen causal scanner rows. It does **not** score a stock, select a top-N list, permit a trade, change size, or modify the frozen scanner or Micro policies.

## What is measured

The extractor records, at each decision minute:

- the full-membership percentage-gain leader and the candidate's rank;
- leadership changes and observed leader tenure;
- whether the candidate became or remained the leader;
- the count of already-active upstream market candidates and how many rank ahead of the candidate;
- minute-to-minute rank, gain, leader-gap, and cumulative-volume changes when exact consecutive bars exist; and
- elapsed time since causal market qualification.

There is no combined attention score and no fitted threshold. A missing exact candidate bar remains missing; rank may still be carried by the frozen scanner, but gain and volume deltas stay null.

## Frozen two-date validation

The extractor reproduced one output row for every source scanner row: 511 rows on 2025-04-03 and 1,702 rows on 2026-07-09. The source was the successful frozen scanner artifact from workflow run `32030416481`, artifact `9288797201`, ZIP SHA-256 `dd05dcd58bd3adc20e18416035b2c6b4c517fb57d5d853d63c2b327d1b2a1d12`.

| Case | Causal observation | What it means |
|---|---|---|
| TIVC, 2025-04-03 | Activated at full-membership rank 15, reached a best rank of 12, and never became rank one. RGC remained the recorded leader for all 180 minutes. | Rank one cannot be made a universal Ross participation rule from the current evidence. The extreme RGC gain also shows that raw gain rank can be a noisy attention proxy. |
| VRAX, 2026-07-09 | Activated at 11:32 UTC at rank two. Frozen provider news first became available at 11:34:33, appeared in the 11:35 decision row, and VRAX replaced MNST as leader at 11:38. It then held rank one for 142 observed minutes. | The feature layer captures a real leadership handoff and persistence. It does not reproduce Ross's reported proprietary scanner alert about 15 seconds after news, so market qualification, provider news timing, and human attention remain distinct layers. |

The VRAX timing mismatch is informative, not something to tune away. The upstream market gate recognized the stock before the frozen news feed did, while Ross described a news-linked scanner event at a lower price. That means we still need to model the interaction among market motion, catalyst arrival, scanner presentation, and human judgment rather than treating any one feed as the decision.

## Causal boundary

Every feature uses only rows available at the current or immediately prior decision minute. Later candidate activation cannot rewrite earlier features. Nonconsecutive observations reset deltas and tenure. Ross's reported entries, fills, reasons, and outcomes are used only afterward for interpretation.

## What remains missing

These features do not observe Ross's proprietary scanner, watchlist, real-time audio commentary, Level 2, tape, chat-room attention, or a complete set of stocks he considered and rejected. The source snapshot covers only two dates, so it is not representative enough to fit an attention rule.

The next defensible step is to run the same label-blind features on a preregistered broader date panel and compare attention states with independently extracted pre-entry decisions. Until then, the extractor is a research instrument, not a strategy component.
