# Context held-out component comparison v0.1

Status: **frozen descriptive comparison; protocol gate complete; no fit, score, runtime change or policy promotion**.

## Frozen inputs and neutral anchor

The comparison binds retrospective labels `3ff85b371de31ea5dc1d2e4afc4e334c6f6f5051bfe5c7340fb51007527b7cd1`, deterministic runtime ZIP `a29186eb092752cfafc031360cacf348bea5e607cb19ce326ddaff2ddfedac1a`, snapshot runtime `6dcc6f25ddb73e63b5f9c714e0c890ab954b15b099e7ba3a71ef948f9760939f`, semantic manifest `9b3be7a17f29e638b0e1da14b4d050762503bab17c74c3f97e62b99489f25cd4` and semantic rubric `959256aedcc7ed89c8120b19cd1640547a63eb24fcca359c476117ba679f13d3`.

All 314 semantic records pair with the exact 314 deterministic snapshot keys and source hashes. Their 2,545 evidence references all resolve to an evidence item in the bound snapshot.

Retrospective recaps do not establish synchronized decision timestamps. The comparison therefore uses the first `candidate_activation` snapshot as the one neutral anchor shared by all 195 candidates. It does not claim activation is trade time and does not search the 119 later source-change snapshots for a more favorable match.

## Deterministic coverage

| Evidence domain | All snapshots (n=314) | Activations (n=195) | Explicit labeled symbol-dates (n=18) |
|---|---:|---:|---:|
| Scanner market | 314 | 195 | 18 |
| Attention / leadership | 314 | 195 | 18 |
| Catalyst chronology | 314 | 195 | 18 |
| Provider headline | 254 | 135 | 14 |
| Daily chart | 285 | 195 | 18 |
| Theme / regime | 314 | 195 | 18 |
| Filing corroboration | 0 | 0 | 0 |
| Issuer-event history | 0 | 0 | 0 |
| Dedicated liquidity domain | 0 | 0 | 0 |
| Account state | 0 | 0 | 0 |
| Portfolio attention | 0 | 0 | 0 |

All news chronology calls report provider success. The 29 absent daily-chart domains occur on later source-change snapshots whose exact candidate bar was unavailable; no activation snapshot lacks daily evidence and no price was imputed. Float provenance remains explicit: among 195 activations, 187 have selected SEC evidence, seven have no eligible SEC evidence and one issuer has no SEC companyfacts result.

## Semantic activation coverage

Across the 195 activation snapshots:

- catalyst substance is assessed on all 195, including 60 provider-relative no-event states;
- commitment is assessed on 135 and abstains on the same 60 no-headline activations;
- leadership and chart cleanliness are assessed on all 195;
- credibility/repetition and theme-fit/no-news acceptance abstain on all 195 because their required semantic evidence is absent; and
- no axis emits a score, rank, selection, order, size or risk action.

The four explicit account groups remain separate:

| Account action | n | Headline present | Definitive commitment | Near resistance / failed-pop history | Credibility abstains | Theme-fit abstains |
|---|---:|---:|---:|---:|---:|---:|
| Main participated | 11 | 8 | 3 | 5 | 11 | 11 |
| Main explicit rejection | 4 | 4 | 0 | 3 | 4 | 4 |
| Small participated | 6 | 4 | 2 | 3 | 6 | 6 |
| Small explicit rejection | 8 | 6 | 1 | 7 | 8 | 8 |

These are contingency counts, not accuracy estimates. Trade and rejection groups overlap across catalyst, chart and leadership values. The panel is too small and sparse to turn those overlaps into weights, thresholds or a selection rule. The complete value, confidence, citation and abstention distributions remain in the machine-readable artifact.

## Candidate acquisition remains separate

The causal scanner acquired 11 of 17 observed main-account completed-trade actions and 6 of 9 small-account completed-trade actions. Across accounts, it acquired 12 of 18 unique observed completed-trade symbol-dates. Off-candidate actions retain no deterministic or semantic component claims.

This acquisition diagnostic cannot be combined with the context axes into an overall imitation score. Missing account state, divided attention and portfolio constraints also mean the context snapshot cannot explain why the main and small accounts sometimes made different decisions on the same symbol.

## Result and next gate

The comparison content SHA-256 is `d93d61ed0ebd5657bbed135beb7fe2d7b0f337d1e3f76720c0f1dcff7908ff54`.

The registered context protocol sequence is now complete. The next valid engineering gate is to add causal campaign, portfolio and account-state representation so repeated Micro emissions can be consolidated into decisions an account could actually take. Micro-v0.1 remains immutable, and any future semantic or technical rule remains a separately named, preregistered experiment.

## Files

- Comparison artifact: `research/data-audits/context-heldout-comparison-v0.1-2026-08-19.json`
- Builder: `scripts/summarize_context_heldout_behavior.py`
- Validator: `src/momentumbot/research/context_heldout_comparison.py`
- Tests: `tests/test_context_heldout_comparison.py`
