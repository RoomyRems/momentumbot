# Discretion held-out panel v0.1

Status: **label-blind runtime frozen; human review not started; no trading authority**.

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

## Replayability checkpoint

Before acquiring the ten registered dates, the scanner builder now supports a separate deterministic source-input sidecar. It saves the exact canonical inputs behind the existing scanner source hash and can reproduce scanner rows without refetching those inputs from the provider. The frozen two-date scanner workflow validates this path before it is used for the held-out pilot. Details are in `docs/research/scanner_source_inputs_v01.md`.

## Label-blind runtime acquisition

The dedicated held-out workflow acquires all ten fixed dates without opening Ross labels. It verifies each date against a provider-observed SPY session, builds point-in-time membership, market, float, news and scanner artifacts, and persists the scanner input sidecar. The frozen identity rule is applied independently on every date; the first and last dates provide the interval-wide alias and corporate-action audit boundary. Intermediate symbol transitions that are not visible at either endpoint remain a documented pilot limitation rather than being guessed.

The acquisition completed successfully in workflow run `32071946359`. The frozen artifact contains 119 causal market candidates and 12,440 candidate-minute scanner rows. All ten dates passed the active loaders, provider-independent scanner replay and temporal checks. No Ross action, outcome or P&L label was used. The permanent audit is `research/data-audits/discretion-heldout-runtime-v0.1-2026-08-17.json`.

## Provider-free discretionary context

The next frozen layer derives three descriptive shadow artifacts from that exact runtime: attention/leadership state, provider-news chronology and causal headline evidence packets. These artifacts retain every market candidate and have no score, threshold, order authority or risk authority. They are evidence for the later human comparison, not a trading rule.

## Frozen Micro activity checkpoint

The final label-blind prerequisite replays the unchanged `micro-v0.1` policy for all 119 causal candidates. It uses each candidate's completed-minute qualification time, derives ten-second bars from SIP trades, and permits action only after a ten-second bar is fully known and before the 10:00 ET cutoff. It preserves the trade tape, derived bars and completed-minute support inputs so the result can be replayed rather than inferred from summary counts.

This checkpoint measures plan emissions, modeled fills and the number of candidates on which the technical policy acts. A plan emission is not treated as a portfolio trade: successive bars may emit repeated plans during one momentum campaign, and this layer does not model buying power, position state, divided attention, Level 2 or discretionary catalyst judgment. Provider-unavailable cases remain separate from genuine zero-plan cases.

The workflow remains label-blind and does not change any Micro threshold. Its output must be frozen before the retrospective Ross review begins. That ordering prevents the human trades from influencing how much technical setup activity the bot is allowed to generate.
