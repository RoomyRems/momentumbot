# Early-pullback paired adapter v0.1 — synthetic mechanics verified

## Purpose and frozen parent

This step starts from `2a675a6adae46f384341c7dc9a4921b4f00c6606`, tree
`43d0b57623c58b0048869c8c6cefb0f02fe75ea7`. It implements normalized causal
trigger binding and tests two independent account arms with the final original
terminal-continuation engine. It does not evaluate the new historical panel.

The one mechanical question is whether original causal inputs can reproduce
the unchanged Micro trigger and whether applying the registered first-two gate
can produce independently carried account paths without changing execution,
risk, fees or management. The [selection registration](early_pullback_selection_v01.md)
and its exact 30 dates, all 24 paths and primary comparison are unchanged.

The intended project remains a hybrid of deterministic mechanics and crucial
discretionary/context components. Interim results describe the components
actually integrated; the incomplete baseline does not settle the full hybrid's
edge. Adding the missing components is necessary research, not a guarantee of
Ross-like returns or eventual profitability. This boundary is now in
`AGENTS.md` as a standing instruction.

Transcripts may clarify offline, versioned strategy design. Recap actions,
fills, future outcomes and evaluation-case narratives must stay out of replay
and runtime AI prompts, and registered evaluation cases cannot tune this frozen
experiment. No transcript records were needed or opened for this step.
Discretion remains a separate descriptive shadow and is not integrated here.

## What the source binding proves

`authenticate_trigger` requires externally frozen hashes for the normalized
source envelope, original activation and original decision. It admits only
activation/decision records and structured SIP trades, completed session
minutes and prior-session EMA warmup. Extra outcome/label fields are rejected.

The adapter reconstructs ten-second bars and completed-minute support, then
calls the original Micro trigger builder. The entire original plan, stop,
first trigger, activation/profile identity and complete Micro-prefix hash must
reproduce. It recomputes the original pullback ordinal on the same plan prefix.
Tied trade timestamps preserve receive order; earlier crossings cannot be
hidden behind a later decision. Future trades, incomplete support bars and
same-session warmup are rejected.

These are normalized-source integrity and reconstruction checks. An expected
hash supplied by the same untrusted producer is not independent evidence.
Raw provider archives, normalization factors and scanner cross-section
completeness still need their own point-in-time provenance adapter. This child
does not claim to authenticate those dependencies.

## What the paired mechanics prove

`replay_synthetic_pair` accepts pinned original-catalogue synthetic programs
and synthetic symbols only. It reconstructs all available trigger bindings
before either arm runs; available sources cannot be silently omitted. Both
arms retain original unavailable references and inspect the same source union.

The control follows the original engine. In the child, a late-pullback
withhold occurs at the original decision time and rank before capacity/risk
evaluation. It creates no order, capital reservation, fee or campaign entry.
Both arms still traverse and validate withheld opportunities' source streams,
so a late source error remains an input failure.

Each arm receives its own once-only seed, account machine, cash, positions,
fees and previous-close chain. Withholding an opportunity can free capacity
for another symbol. A control position left open can block its next session
while the child independently continues flat. The implementation never
subtracts excluded fills from a saved baseline or borrows control balances.

Tests compare admitted decisions, events, processed streams and account state
with the original parent, including both accounts and both execution scenarios.
A separate existing Decimal checker verifies 16 account snapshots across four
two-session cases. That check independently reconciles account arithmetic;
it is not a second independent fill simulator.

## New historical dates remain a separate integration task

The ancestor account validator pins its original date catalogue, session
indices and seed ancestry. Those guards are unchanged. The new March–May 2026
dates have not been mapped onto old 2025 slots or passed through relaxed guards.
Synthetic fixtures exercise the original catalogue without historical prices.

Before the registered new panel can run, an isolated catalogue/source adapter
must bind its dates, independently confirmed sessions, point-in-time scanner
population, normalization and raw sources to the account engine. The existing
synthetic program entry point does not enable that historical execution.

## Exact availability plan, with no calls yet

The [frozen data plan](../../research/data-audits/early-pullback-paired-adapter-v0.1/data-plan.json)
defines four candidate calls with no retries or pagination:

| Provider | Fixed request | Limited evidence sought |
|---|---|---|
| Alpaca SIP | SPY raw daily bars, March 3–May 21, 2026; as-of May 19; ascending, limit 1,000 | SIP entitlement and date presence |
| Massive | Active US stock membership dated March 4, 2026; ticker ascending, limit 1 | Point-in-time endpoint availability |
| Massive | Same membership sample dated May 19, 2026 | Point-in-time endpoint availability |
| Databento | `metadata.get_dataset_range` for `XNAS.ITCH` | Dataset interval metadata |

All exact parameters are in the plan. These limited probes cannot establish
full-session coverage or a complete cross-section. Only availability, counts
and dates would be projected; raw prices, tickers and outcomes would not be
persisted. Transport is not implemented, authorized calls are zero, and no
provider call or paid acquisition was performed.

Acquisition request counts and costs remain unknown. Zero authorized spend
does not mean data are free. After catalogue/source planning, freeze the
shared source requests and trigger-bound execution/management windows, obtain
metadata quotes, and bind per-request and total ceilings before separately
authorizing a one-shot capture. The exact selected dates cannot be replaced.

## Verification and preserved evidence

Registration:
`989cd51227088010ad1c95db028bb9f876ee23fed94aeb62bcf038af584e8b6c`.

Data plan:
`41d941377a8a53ccc250f03e406aaf5419e868df0eb64f6e67331b3fae1a4a16`.

The registration checks 314 file bindings, including the original terminal
account ancestry and this child's implementation. Provider-free verification:

```bash
PYTHONPATH=src:scripts python -O scripts/build_early_pullback_paired_adapter_v01.py
PYTHONPATH=src:scripts python -m unittest tests.test_early_pullback_paired_adapter_v01 -v
```

All 24 focused tests pass in 4.469 seconds with pandas 2.2.3/NumPy 2.3.5 and
in 4.451 seconds with assertions disabled under pandas 3.0.5/NumPy 2.5.3.
All 2,523 local full-suite tests pass in 274.204 seconds with zero skips.
Compilation, optimized registration validation and the independent account
check pass. The suite covers source/plan forgery, causal clocks, ordinal
selection, independent capacity/cash/open-state carry, unavailable sources,
trailing failures and rehashed result tampering. Empty synthetic paths cover
both arms across all 12 original path combinations and 30 catalogue slots.

An initial 20-test run had 19 errors because the synthetic pullback candle had
no valid red/decreasing pause. The original evaluator correctly rejected it.
Changing only the fixture's open from 9.2 to 9.7, above its 9.5 close, made the
20 tests pass; subsequent cases expanded coverage to 24. The exact initial
fixture source, failed log and all later verification logs are preserved in
the [implementation verification](../../research/data-audits/early-pullback-paired-adapter-v0.1/implementation-verification.json).
Hosted results remain separate publication-commit checks.

The losing parent results, all existing source evidence and the user's
hosted-only waiver of another local historical account replay remain intact.
No new financial evaluation, historical account replay, transcript-label join,
provider access, brokerage order or policy promotion is enabled. Next is the
isolated new-catalogue/source integration, followed by the bounded availability
and quote/capture gates.
