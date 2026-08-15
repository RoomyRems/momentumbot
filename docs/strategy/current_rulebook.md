# Current-era strategy rulebook — bootstrap version

This is the current research map extracted from the corpus. `research/rules/current_rules.json` contains the **first machine-validated subset** that is safe to consume in code; the broader table below is the candidate registry still being evidence-reviewed before promotion. This is deliberately staged so an attractive idea does not become executable policy merely because it appeared in a transcript.

## Core hierarchy

```text
market regime
    -> attention / obvious stock
    -> five-pillars qualification
    -> catalyst + daily-chart context
    -> momentum phase
    -> setup / entry trigger
    -> Level 2 + execution quality
    -> session risk state
    -> starter / add-to-strength
    -> deterioration-driven exits
    -> campaign journal and replay
```

## Candidate rule registry

| Rule | Policy | Role |
|---|---|---|
| MB-SEL-001 | Candidate already up at least 10% | Deterministic |
| MB-SEL-002 | RVOL at least 5x for current baseline | Deterministic |
| MB-SEL-003 | Core price band $2-$20; $5-$10 preferred | Deterministic/ranking |
| MB-SEL-004 | Current baseline prefers float under 10M | Deterministic |
| MB-SEL-005 | Fresh news normally required for A-quality; explicit exceptions exist | Mixed |
| MB-SEL-006 | Prefer the market's obvious attention leader | Mixed |
| MB-CAT-001 | Score catalyst substance and theme novelty | AI-context candidate |
| MB-DLY-001 | Require enough daily-chart room for the planned reward | Deterministic |
| MB-ENT-001 | First-pullback quality: <=~50% retrace, good volume profile, VWAP/9 EMA support, limited rejection | Deterministic |
| MB-ENT-002 | Canonical trigger: first candle to make a new high | Deterministic |
| MB-ENT-003 | Prefer first/second pullbacks; penalize later extension | Deterministic |
| MB-POS-001 | Start smaller and add only after confirmation/strength | Deterministic |
| MB-RSK-001 | Logical stop + ~2:1 plausible reward after actual fill/slippage | Deterministic |
| MB-EXE-001 | Recalculate/abort when slippage invalidates the plan | Deterministic |
| MB-MIC-001 | Detect hidden-seller absorption / impact mismatch | Mixed, later Level-2 phase |
| MB-MIC-002 | Avoid both unmanageably thin and immovably thick liquidity | Deterministic feature set |
| MB-EXT-001 | Let strong winners run until deterioration; no unconditional fixed full-exit target | Mixed |
| MB-RSK-002 | Build a session cushion before full size | Deterministic risk state |
| MB-RSK-003 | Stop after giving back half of meaningful session high-water profit | Deterministic hard guard |
| MB-RSK-004 | Hard daily max loss; exact calibration must be versioned/tested | Deterministic hard guard |
| MB-RSK-005 | Session exit is terminal for that trading day | Deterministic hard guard |
| MB-RSK-006 | No averaging down | Deterministic hard guard |
| MB-REG-001 | Scale aggression down/up with cold/hot momentum regime | Deterministic research feature |
| MB-REG-002 | No-trade day is valid when quality is absent | Deterministic |
| MB-PHZ-001 | Prefer front-side momentum; model backside/reclaim explicitly | Mixed |
| MB-RES-001 | Raw transcripts are offline research only | Research hard guard |
| MB-RES-002 | Undated transcripts are quarantined from walk-forward work | Research hard guard |

## Promotion policy

A candidate rule is promoted into the machine registry only after its evidence has been checked for publication date, evidence mode (teaching/behavior/self-critique), contradictory examples and deterministic-versus-contextual responsibility. The first promoted subset establishes the schema and chronology controls; subsequent research commits will promote the remaining candidates in evidence-reviewed batches.

## Known conflicts to preserve, not hide

The corpus contains genuine policy evolution and context-dependent differences. Historical float ceilings are often looser than the current under-10M preference, and max-daily-loss calibration is described differently across account sizes and time periods. These are not reasons to add arbitrary configuration. They are reasons to create named policy versions and compare them honestly.

Likewise, beginner teaching is intentionally stricter than experienced discretionary behavior. The baseline should implement the stricter, auditable version first. Exceptions only earn implementation after they improve out-of-sample results without increasing tail risk beyond the risk governor's constraints.
