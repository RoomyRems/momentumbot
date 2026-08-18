# Current project checkpoint

Status applies to the latest validated checkpoint on branch `phase-3-historical-snapshot`.

This file is a routing checkpoint, not a second policy specification. Follow its links to the machine-readable manifests and audits for exact hashes and counts.

## Frozen foundations

- The historical pipeline preserves the decision-time boundary for universe membership, market qualification, float and publication-timed news.
- The causal scanner snapshot and its compact source-input sidecars can be replayed without asking the provider to recreate the scanner features.
- The ten-session held-out panel is preregistered for 2026-07-10 through 2026-07-23. Its label-blind runtime is frozen as artifact `discretion-heldout-runtime-v0.1` (artifact `9305468839`, workflow run `32071946359`).
- That runtime retains all 119 causal market candidates and 12,440 scanner decision rows. No top-N selection, Ross action, trade outcome or later price outcome was used.
- The frozen technical parent remains `micro-v0.1`, fingerprint `49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa`.
- Its ten-session Micro replay is frozen as artifact `discretion-heldout-micro-runtime-v0.1` (artifact `9310627233`, workflow run `32096497787`, ZIP SHA-256 `3b59e4b1a69e268158f6ccbead1fe9abae425fc249e72b34f466e53ebba56b20`). Of 119 candidates, 118 were replayable, 49 produced at least one plan and 36 produced at least one modeled fill; LIVE was correctly isolated as provider-unavailable rather than counted as a zero-plan case.
- Catalyst timing, catalyst evidence, catalyst interpretation and attention/leadership exist as descriptive shadow context. They have no order, score, threshold or risk authority.
- Retrospective evidence is frozen for all ten dates from the supplied 300-record caption batch. Main and small accounts remain separate, ticker corrections are explicit, and unmentioned candidates remain unknown. The label content SHA-256 is `4dd31df3fcace0bcc0b52045c748a1a91e00130867394e21c605af5f42007204`.
- The frozen component comparison has content SHA-256 `809d4b4a7231b708f9c933c9bf45b58c736f4d3101c8328483c62c1c48bcfb3d`. Micro-v0.1 modeled fills on 6/9 acquired documented trades in each account, but also fired on 2/7 main-account skips and missed three documented decisions per account. The scanner acquired 11/13 unique observed traded symbol-dates. No rule was retuned or promoted.

Exact provenance lives in:

- `research/data-audits/discretion-heldout-runtime-v0.1-2026-08-17.json`
- `research/data-audits/discretion-heldout-micro-runtime-v0.1-2026-08-17.json`
- `research/data-audits/discretion-heldout-labels-v0.1-2026-08-18.json`
- `research/data-audits/discretion-heldout-comparison-v0.1-2026-08-18.json`
- `research/strategy/discretion-heldout-panel-v0.1.json`
- `docs/research/discretion_heldout_panel_v01.md`
- `docs/research/discretion_heldout_labels_v01.md`

## Active gate

Translate the now-observed missing context into preregistered, label-blind shadow assessments without changing Micro-v0.1:

1. keep measurable facts deterministic: leadership/rank transitions, news chronology, daily levels, account state, liquidity and session timing;
2. define structured causal evidence packets for genuinely semantic judgments such as catalyst substance, credibility, theme fit and whether the opportunity is becoming obvious;
3. evaluate deterministic translations and any AI shadow assessment on a new out-of-sample panel rather than fitting the ten sessions just reviewed;
4. require AI to cite only the time-causal structured evidence it received, permit abstention, and give it no order or risk-increase authority; and
5. keep candidate acquisition, contextual selection, Micro setup and execution as separate measurable gates.

The ten-session result is a component diagnostic, not a portfolio backtest. Repeated plans can belong to one campaign, and buying power, divided attention, Level 2, tape-based management and complete exits are still absent.

## Next gates

1. Freeze the first causal context-assessment protocol and run it shadow-only on a new held-out panel.
2. Add campaign/portfolio/account state so repeated Micro emissions are consolidated into decisions Ross could actually take.
3. Add realistic execution and latency, then Level 2/time-and-sales capture and deterministic summaries where historical or live data permits.
4. Validate any AI contribution out of sample and in live shadow before it can affect paper decisions.
5. Run a larger preregistered walk-forward panel before considering policy promotion or interpreting P&L.

## Explicitly not ready

- No claim of exact Ross imitation or comparable profitability.
- No production selection authority for AI.
- No complete Level 2/tape, position-management or broker-execution model.
- No live-money trading.
