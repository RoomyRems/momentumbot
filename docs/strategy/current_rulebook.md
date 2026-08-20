# Current-era strategy rulebook — evidence-backed bootstrap

The machine-readable source of truth is the bundle manifest `research/rules/current_rules.json` plus the category files under `research/rules/current/`. This registry contains rules that have been explicitly reviewed against the enriched transcript corpus. It is intentionally smaller than the full corpus: evidence promotion is a quality-control step, not a keyword extraction exercise.

## Decision hierarchy

```text
market regime
  -> attention / five-pillars candidate quality
  -> catalyst + daily context
  -> front-side momentum state
  -> first/early pullback structure
  -> confirmation trigger + fill-quality check
  -> deterministic risk governor
  -> chart/tape deterioration exits
  -> campaign/session journal
```

## Promoted rules

| Rule | Policy | Responsibility |
|---|---|---|
| `MB-SEL-001` | The current general five-pillars baseline requires a stock to already be up at least 10% on the session. | Deterministic |
| `MB-SEL-002` | The current general five-pillars baseline requires relative volume of at least 5x normal volume; higher is preferred. | Deterministic |
| `MB-SEL-003` | The current general strategy focuses on $2-$20 stocks, with roughly $5-$10 described as an especially attractive range. | Deterministic |
| `MB-SEL-004` | The current general five-pillars baseline prefers float below 10 million shares, with lower generally better. | Deterministic |
| `MB-SEL-005` | Fresh company news is part of the current A-quality five-pillars screen. A no-news stock may be considered conditionally when it becomes the unmistakable market leader, but that is an exception rather than A-quality. | Mixed |
| `MB-SEL-006` | High total volume improves tradability and is strongly preferred, but it is not one of the canonical five pillars in the current full-training definition. | Deterministic |
| `MB-SEL-007` | The January 2026 small-account challenge intentionally tightened the general strategy toward roughly $1.50-$6, at least 25% gain, at least 5x RVOL, float under 10M, and top-three gainer status. | Deterministic |
| `MB-SEL-008` | Prefer the market's obvious attention leader. | Mixed |
| `MB-TIM-001` | Focus new entries from 7:00 a.m. to about 10:00 a.m. Eastern. | Deterministic |
| `MB-IND-001` | MACD uses standard 12/26/9 settings with close as source. | Deterministic |
| `MB-PHZ-001` | Prefer front-side long momentum; use negative MACD/backside and later reclaim as explicit states. | Deterministic |
| `MB-ENT-001` | First-pullback quality: <=~50% retrace, contracting pullback volume, VWAP/9 EMA support, limited topping-tail rejection. | Deterministic |
| `MB-ENT-002` | Canonical trigger: first candle to make a new high. | Deterministic |
| `MB-ENT-003` | Logical stop: pullback low. | Deterministic |
| `MB-ENT-004` | Require about 2R plausible room to prior high before entry. | Deterministic |
| `MB-ENT-005` | Micro pullback is the one-candle version of the same pattern. | Deterministic |
| `MB-ENT-006` | Prefer first/early pullbacks; penalize later extension. | Deterministic |
| `MB-POS-001` | Start with a starter and use a successful first trade as a cushion before greater aggression. | Deterministic |
| `MB-POS-002` | Do not average down. | Deterministic |
| `MB-EXE-001` | Recalculate/abort when actual slippage destroys planned reward/risk. | Deterministic |
| `MB-EXT-001` | Do not impose an unconditional fixed full-exit profit cap. | Mixed |
| `MB-EXT-002` | Exit evidence includes large/hidden sellers, red tape, false breakouts, slowing buys, topping tails and red candles. | Mixed |
| `MB-MIC-001` | Hidden-seller absorption is an executed-volume/price-impact mismatch. | Mixed, later Level-2 phase |
| `MB-REG-001` | Model cold -> spark -> hot/sustained -> exhausted market-cycle states. | Mixed |
| `MB-REG-002` | Throttle aggression by demonstrated market regime. | Deterministic |
| `MB-RSK-003` | Stop after giving back half of meaningful session high-water profit. | Deterministic |
| `MB-RSK-004` | General max daily loss is calibrated around recent/typical average daily gain. | Deterministic research calibration |
| `MB-RSK-005` | Once the session is ended, do not return later that day. | Deterministic |
| `MB-CAT-001` | Judge catalyst substance/context, not merely fashionable headline keywords. | AI-context candidate |
| `MB-RES-001` | Raw transcripts are offline research only. | Research hard guard |
| `MB-RES-002` | Undated transcripts are quarantined from walk-forward work. | Research hard guard |

## Interpretation rules

- **A-quality is not the same as four-of-five.** Current training describes all five pillars as the A-quality standard. The later four-of-five language is preserved as a conditional exception; the deterministic baseline currently implements only the strongest documented missing-news/#1-gainer exception rather than allowing any arbitrary missing pillar.
- **Total volume is tracked but is not promoted to a sixth pillar.** The current full-training definition is gain, RVOL, news, price, and float. Total volume is an additional liquidity/quality preference.
- **Small-account thresholds are a named profile.** The stricter 2026 challenge screen is not allowed to silently replace the general strategy.
- **2R is an entry-quality requirement, not a mandatory full exit.** The OHLC-only baseline lets winners continue until chart deterioration, while Level-2/tape exits remain deferred.
- **The raw transcripts are offline evidence only.** Neither historical replay nor the future AI reviewer can retrieve retrospective recap text.

## Explicit research translations still needing ablation

The corpus does not provide a unique algorithm for every visual judgment. The current deterministic baseline therefore isolates the following translations so they can be challenged rather than hidden:

- machine identification of the impulse base used for the 50% retracement calculation;
- the numeric definition of a “large” topping tail;
- exact historical-news freshness window when constructing daily snapshots;
- deterministic market-regime scoring;
- daily-chart resistance clustering and “room” scoring;
- Level-2 absorption thresholds and tape-velocity thresholds.

These are not optimization invitations. Each translation will have a small set of pre-declared alternatives and will be evaluated out-of-sample.
