# Theme/regime context shadow v0.1

Status: **frozen deterministic schema and builder; no held-out runtime artifact, hot/cold threshold, theme-fit rule, score, or trading authority**.

## Research question

Can the project represent the market context surrounding a candidate—how crowded the same-minute leaderboard is, whether leaders have provider news, whether headlines connect multiple active candidates, and how active recent completed sessions were—without retrospectively declaring that the market was “hot,” inventing a theme, or exposing recap behavior?

The evaluation panel remains the ten calendar-fixed sessions in `ross-context-heldout-panel-v0.1`. The schema was frozen before inventorying or opening any recap source for those dates.

## Causal sources

The packet uses only:

- exact causal scanner rows at the candidate's decision minute;
- publication-timed Alpaca/Benzinga news events available no later than that decision; and
- hash-bound summaries of at most five strictly earlier completed scanner sessions.

The same-minute scanner cohort retains each active candidate's rank, gain, price, RVOL, volume, activation time, market-leader state, and provider-relative news state. Headline stories retain their exact title and provider associations. A story associated with multiple active candidates is recorded as a cross-candidate association, not classified as a market theme.

Each prior-session summary records candidate count, activation chronology, final provider news/no-news/error counts, rank-input coverage, and the final observed rank leader. A prior session's final scanner state is permissible only on later dates, when that completed history was already known.

## What is deliberately not defined

The contract freezes no:

- hot/cold market threshold or label;
- minimum activity count;
- theme taxonomy or theme-fit rule;
- no-news acceptance threshold;
- aggregate context score; or
- selection, recommendation, order, sizing, or risk action.

Provider-relative no-news remains exactly that: no eligible story in the frozen provider tape by the decision time. It is never upgraded to universal proof that no catalyst existed.

An eventual AI shadow may cite this packet for the registered `theme_fit_no_news_acceptance` axis and may abstain. It cannot place an order, prioritize a candidate, or increase risk.

## Causal validation

The builder fails closed when same-minute scanner rows disagree on their rank lineage or market leader. Future scanner rows are excluded from the packet. Future headlines are projected out. Prior-session summaries must be independently hash-valid, unique by date, and strictly earlier than the decision session.

The complete packet retains its exact scanner rows, available headline stories, prior summaries, source-artifact hashes, and a deterministic content hash. Rehashing a modified derived feature does not make the record valid because validation reconstructs it from the retained inputs.

## Next valid step

Build the registered panel's label-blind market/scanner runtime. Then materialize daily-chart and theme/regime records at candidate activation and causal news-change decisions, freeze their aggregate hashes, and compose context snapshots. Only after every deterministic and optional semantic shadow artifact is frozen may recap inventory begin.

## Files

- Contract: `research/strategy/theme-regime-context-shadow-v0.1.json`
- Builder and validators: `src/momentumbot/research/theme_regime_context.py`
- Registration audit: `research/data-audits/theme-regime-context-shadow-v0.1.json`
- Tests: `tests/test_theme_regime_context.py` and `tests/test_context_assessment.py`
