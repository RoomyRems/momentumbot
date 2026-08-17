# Discretion held-out panel v0.1

Status: **registered and unlabeled; no trading authority**.

## Why this is the next step

The existing examples show that Ross's decisions depend on more than a ten-second chart pattern. Catalyst substance, which stock is becoming obvious, the broader market theme, daily-chart resistance, liquidity, account state and execution quality can all change whether he trades or waits.

Those examples were useful for discovering the missing layers, but they were already known when the research rules were written. They therefore cannot be used as an honest final test of those rules.

This registration fixes that problem before more source material is reviewed. It freezes the first ten registered U.S. equity sessions after the latest development case, July 9, 2026:

`2026-07-10`, `2026-07-13`, `2026-07-14`, `2026-07-15`, `2026-07-16`, `2026-07-17`, `2026-07-20`, `2026-07-21`, `2026-07-22`, and `2026-07-23`.

The dates were chosen without symbols, Ross actions, outcomes or P&L. The upstream session calendar must still verify each date before runtime acquisition.

## Required order

1. Run the market, scanner and shadow-context reconstruction without Ross labels.
2. Retain every causally market-qualified candidate; do not apply a top-N filter.
3. Freeze and hash the runtime artifacts.
4. Only then locate and review Ross's evidence for those fixed dates.
5. Store human actions in a separate retrospective artifact.
6. Compare the two frozen sides without changing the rules.

If a recap is missing, that date remains in the panel and is marked `source_unavailable`. It is not replaced with a more interesting day.

## What counts as a skip

An unmentioned stock is not a skip. Ross may omit candidates from a recap, or may never have seen them. The allowed states are:

- participated;
- explicitly skipped or rejected;
- discussed but the action is unclear;
- not mentioned or unobservable; and
- source unavailable.

Only the first two states can enter a trade-versus-skip comparison. Main-account and small-account decisions are reported separately because buying power, broker behavior and divided attention can change the action.

## What this pilot can establish

The pilot can test whether the causal acquisition and labeling process works, measure evidence coverage, and show how individual shadow features behave on explicit trades and skips. It must also report plan/fill activity so a broad rule cannot look better merely by firing more often.

It cannot fit a catalyst score, attention threshold or new Micro rule. Ten sessions are not a representative walk-forward sample, and this registration cannot support policy promotion or a full claim that the bot mimics Ross.

The machine-readable registration is `research/strategy/discretion-heldout-panel-v0.1.json`.

