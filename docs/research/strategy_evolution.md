# Strategy evolution notes

The corpus supports a strategy that is stable in concept but not frozen in thresholds. These notes exist to prevent accidental cherry-picking across eras.

## Stable concepts

- “First pullback” language appears throughout the corpus going back many years and remains central in current training.
- The method consistently emphasizes low-float momentum, unusual volume, a defined pullback invalidation level, and trading the strongest/most obvious stocks.
- Giveback/walk-away discipline appears repeatedly over many years.

## Threshold evolution

Simple phrase discovery shows both 2x- and 5x-RVOL language historically, while five-times RVOL becomes particularly common in recent training and is the explicit current full-training floor. Float ceilings likewise vary across older material (50M/20M/10M references), whereas current full training states less than 10M for the canonical five-pillars baseline.

Because these are policy changes rather than independent features, MomentumBot represents them as named eras/profiles. We will not run a giant grid over every historical threshold and report whichever wins.

## Front-side formalization

“Front side” terminology becomes especially prominent in recent years. Current material explicitly uses one-minute MACD state to help distinguish front-side long momentum from backside conditions and potential later reclaims. The standard MACD inputs are explicitly taught as 12/26/9 using close.

## Current baseline source hierarchy

When current sources disagree in strictness, the deterministic baseline uses the stricter auditable rule and records the looser behavior as a conditional exception. The clearest example is all-five-pillars A-quality versus the later statement that four-of-five may still be traded cautiously. The initial exception implemented in code is the specifically documented no-news case when the stock is the unmistakable #1 gainer.
