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

Exact provenance lives in:

- `research/data-audits/discretion-heldout-runtime-v0.1-2026-08-17.json`
- `research/data-audits/discretion-heldout-micro-runtime-v0.1-2026-08-17.json`
- `research/strategy/discretion-heldout-panel-v0.1.json`
- `docs/research/discretion_heldout_panel_v01.md`

## Active gate

Encode Ross's documented behavior retrospectively, without changing the already-frozen runtime:

1. locate the available recap or primary source for each of the ten fixed dates;
2. record small-account and main-account actions separately;
3. use only the preregistered states: participated, explicitly skipped/rejected, discussed but unclear, unmentioned/unobservable, or source unavailable;
4. never convert an unmentioned candidate into a skip;
5. freeze the evidence citations and labels before comparing them with scanner, Micro or discretionary-shadow features; and
6. make no threshold or policy changes from this ten-session diagnostic.

This gate tests evidence coverage and behavioral alignment. It is not yet a portfolio backtest: repeated plans can belong to one campaign, and buying power, divided attention, Level 2, tape-based management and complete exits are not modeled here.

## Next gates

After the retrospective evidence is frozen:

1. compare Ross behavior against the already-frozen scanner, Micro and discretionary-shadow evidence without retuning them;
2. decide which contextual judgments merit a preregistered deterministic translation and which merit an AI shadow assessment;
3. validate any AI contribution out of sample before it can affect paper decisions;
4. add campaign/portfolio state, Level 2/tape inputs where available, and realistic execution before interpreting P&L;
5. run a larger preregistered walk-forward panel before considering policy promotion.

## Explicitly not ready

- No claim of exact Ross imitation or comparable profitability.
- No production selection authority for AI.
- No complete Level 2/tape, position-management or broker-execution model.
- No live-money trading.
