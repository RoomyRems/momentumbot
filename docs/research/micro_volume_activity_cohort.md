# Micro volume activity cohort v0.1

## Purpose

The five labeled Micro seed cases show a potentially useful interaction between bounded prequalification context and removal of the hard lower-pullback-volume gate, but they also show substantial activity inflation. A larger label-free cohort is therefore used to stress the activity consequence before considering any further policy work.

This is not called a negative-outcome or false-positive cohort. No human skip/trade labels exist for its candidates, and its conditional candidate gate omits point-in-time float, news and full cross-sectional rank. It can measure how the four already-frozen cells behave after a causal market qualification; it cannot score imitation or full-scanner selectivity.

## Precommitted design

The design is frozen at `research/benchmarks/suites/micro-volume-activity-cohort-v0.1.json` before market discovery.

- Dates are chosen by calendar alone: the second Wednesday of February, May, August and November 2025, then February and May 2026.
- For each date, the first two symbols to causally satisfy the `current-general-2026` price, gain and exact same-time RVOL gate are selected. Symbol ascending is the only tie-breaker.
- Selection never reads later session high, maximum gain, maximum RVOL, micro plans, modeled fills, P&L or Ross behavior labels.
- A date or candidate is never replaced because its replay is inactive, unavailable or unfavorable.
- All four cells for one candidate share the same SIP trades, derived 10-second bars and completed-minute support inputs.

The cells remain unchanged:

| Cell | Prequalification context | Hard lower-volume gate |
|---|---|---|
| Baseline | Off | On |
| Context only | On | On |
| Volume only | Off | Off |
| Context + volume | On | Off |

## Readout contract

The aggregate readout reports paired plan-count and modeled-fill-count deltas, changes in first plan/fill timing and pullback ordinal, and context/volume interaction counts. The volume contrasts are `volume_only - baseline` and `context_plus_volume - context_only`; the context contrasts are `context_only - baseline` and `context_plus_volume - volume_only`.

Each plan is an independently refreshed diagnostic opportunity. Repeated modeled fills do not represent portfolio position state, buying-power limits, campaign re-entry rules or realized P&L.

The cohort is never scored against retrospective behavior labels and is not policy-promotion eligible. A favorable result could justify a separately designed validation stage; it cannot promote either volume-off ablation by itself.

## Completed result

Workflow run `31952684371` completed successfully at design commit `086f4b2ccdda9b3b7f9e8ab86707c0d019544920`. All six discovery jobs, the frozen selection step, all 12 shared-input four-cell replays and the aggregate summarizer succeeded.

The precommitted selection produced 12 candidates across six dates: AIFF, CLMT, ABSI, FNGR, HBM, LPL, RDCM, SI, BETA, LABX, EOSE and GENK.

| Cell | Plans | Modeled fills | Cases with plan | Cases with fill | Median plans/case |
|---|---:|---:|---:|---:|---:|
| Baseline | 31 | 6 | 7/12 | 2/12 | 2.0 |
| Context only | 30 | 4 | 7/12 | 2/12 | 2.5 |
| Volume only | 48 | 7 | 8/12 | 3/12 | 4.0 |
| Context + volume | 51 | 5 | 9/12 | 3/12 | 4.0 |

The paired volume contrasts show the same pattern in both context strata:

| Contrast | Plan delta | Fill delta | Cases with more plans | Cases with more fills |
|---|---:|---:|---:|---:|
| Volume only minus baseline | +17 (+54.8%) | +1 | 6/12 | 1/12 |
| Context + volume minus context only | +21 (+70.0%) | +1 | 7/12 | 1/12 |

Removing the hard volume gate never reduced plan count in either paired contrast. It added a modeled fill only for LPL, at `$4.89` on pullback `#3`. It did not move the first modeled fill for AIFF or EOSE, the two candidates that baseline already filled. FNGR's first plan moved 1,390 seconds earlier without gaining a fill, and the other extra opportunities were likewise mostly non-participating activity.

Prequalification context was not a universally inert factor outside the five-case seed. In EOSE it changed baseline from six plans/three fills with first fill `$10.97`/`#1` to four plans/one fill with first fill `$11.47`/`#4`. In HBM, plans appeared only in the context-plus-volume cell. LABX also received an earlier first plan from context. These candidate-specific structural effects mean the seed-suite interaction cannot be treated as general.

## Post-run audit

An independent code and artifact audit found no retrospective behavior-label leakage and confirmed that every cell within a case used one shared SIP trade tape, derived 10-second bars and support inputs. It also identified two scope limits that sharpen the interpretation:

- Discovery began from Alpaca's currently accessible all-status asset census and current exchange metadata, not a reconstructed point-in-time universe. Delisted, renamed, reused or reclassified historical identities may therefore be absent or misrepresented.
- Ten of the 12 selected cases came from the 07:00 ET acquisition minute. Selection used the earliest qualifying one-minute bucket and then symbol order before SIP refinement, so this is primarily a session-open acquisition-boundary stress sample, not representative scanner-qualified traffic.

The audit also found a timing-label defect in the frozen comparison: `first_plan_latency_seconds` used the source 10-second bar timestamp (`evaluated_at`) instead of the executable plan timestamp (`armed_at`). Absolute first-plan latencies in the frozen summary are therefore 10 seconds early. Because every cell used the same 10-second arming offset, paired first-plan shifts, counts, pullback ordinals, fills and the decision below are unchanged. The cohort reconstructor now retains `evaluated_at` as telemetry but measures onset from `armed_at`.

### Armed-time correction rerun

Workflow run `31984950288` completed successfully at correction commit `cc2521381fffe70804306210cca19b70674ceafe`. It reproduced the same 12 selected candidates, all plan and fill counts, first-fill prices, pullback ordinals and paired shifts. The only numerical changes in the aggregate comparison were the four absolute median first-plan latencies, each exactly 10 seconds later:

| Cell | Original latency (s) | Armed-time latency (s) |
|---|---:|---:|
| Baseline | 1,639.954111 | 1,649.954111 |
| Context only | 1,639.954111 | 1,649.954111 |
| Volume only | 619.950922 | 629.950922 |
| Context + volume | 209.944318 | 219.944318 |

The corrected selection payload is logically identical after excluding per-date discovery content hashes. Its byte hash changed because fresh label-blind discovery changed four of six per-date provenance hashes, not because any selected symbol, qualification time, previous close, rank or case changed. The original frozen artifacts remain intact; the exact corrected selection, summary and provenance are stored under separate armed-time filenames.

### Completed-bar market-discovery rerun

Workflow run `31986483234` attempt 2 completed successfully at timing commit `ff62e61923ae380e53fa29d75610116371a9e51c`. This is a separate label-blind re-acquisition under `causal-market-discovery-v0.2`, not another correction to the same sample. The market-discovery clock now retains the one-minute source-bar start but makes the qualification decision available only at completed-bar time, exactly 60 seconds later. A completed 06:59 ET bar may therefore support a 07:00 decision; a 09:59 bar becomes available at the exclusive 10:00 cutoff and cannot qualify.

The full qualified-symbol sets and counts remained unchanged on all six dates (`8, 38, 26, 28, 18, 31`), but their qualification ordering changed. Five of 12 selected symbols were replaced:

| Date | Armed-time cohort | Completed-bar cohort |
|---|---|---|
| 2025-02-12 | AIFF, CLMT | AIFF, CLMT |
| 2025-05-14 | ABSI, FNGR | IZEA, LUCY |
| 2025-08-13 | HBM, LPL | HBM, UPXI |
| 2025-11-12 | RDCM, SI | RDCM, SI |
| 2026-02-11 | BETA, LABX | LABX, MNTN |
| 2026-05-13 | EOSE, GENK | EOSE, OCG |

LABX moved from q2 to q1. Because cohort membership changed, aggregate differences from the armed-time result are descriptive composition differences, not paired timing effects. Paired A/B/C/D comparisons remain valid within this newly frozen cohort because all four cells still share one market input per case.

| Cell | Plans | Modeled fills | Cases with plan | Cases with fill | Median plans/case |
|---|---:|---:|---:|---:|---:|
| Baseline | 28 | 7 | 6/12 | 3/12 | 1.0 |
| Context only | 26 | 5 | 6/12 | 3/12 | 1.0 |
| Volume only | 46 | 9 | 7/12 | 4/12 | 4.0 |
| Context + volume | 49 | 7 | 8/12 | 4/12 | 4.5 |

The volume contrasts remain adverse activity evidence:

| Contrast | Plan delta | Fill delta | Cases with more plans | Cases with more fills |
|---|---:|---:|---:|---:|
| Volume only minus baseline | +18 | +2 | 5/12 | 1/12 |
| Context + volume minus context only | +23 | +2 | 6/12 | 1/12 |

OCG is the only gained-fill case in either volume contrast. Both volume-off cells produce nine plans and two modeled fills for OCG; the first is `$2.53` on pullback `#8`. The apparent aggregate fill improvement versus the prior cohort is entirely attributable to changed composition: no retained case gained or lost a modeled fill.

The completed-bar source minute also changes some structural ordinals without changing retained-case fills. AIFF moves from first-plan/fill pullbacks `#2/#5` to `#3/#6`, and EOSE moves from `#1/#1` to `#2/#2` in A/C and from `#4/#4` to `#5/#5` in B/D. LABX's A/C first plan moves materially earlier and its plan counts each increase by one. These are acquisition-anchor effects, not evidence that the volume ablation better imitates a human entry.

Nine of 12 selection decisions occur exactly at 07:00 ET from completed 06:59 bars, so the session-open boundary-stress limitation remains. Selection uses completed-bar availability, while replay may use causal SIP intraminute refinement inside an eligible source minute; refinement before the 07:00 strategy boundary is rejected in favor of the 07:00 fallback. The 60-second rule models bar completion and RVOL calculability, not exchange, SIP, provider or network dissemination latency. The UPXI candidate here is dated 2025-08-13 and is unrelated to the labeled Ross benchmark dated 2025-04-21.

## Decision

Do not promote either volume-off cell. The ablation increases setup activity by roughly 55–70% while changing modeled participation in only one of 12 candidates. This is adverse activity evidence, not a convincing reproduction improvement. The frozen `micro-v0.1` policy remains the parent policy.

The separate completed-bar cohort reaches the same decision: disabling the hard volume gate adds 18–23 plans and two modeled fills, with the fills isolated to one late OCG pullback. It does not support promotion.

The experiment does not establish imitation quality, trade quality, realized P&L or full-scanner false-positive rate. The paired results remain valid conditional evidence for these frozen candidates because every cell within a candidate used the same market inputs.

## Frozen artifacts

- Selection: `research/benchmarks/results/micro-volume-activity-cohort-selection.json`
- Aggregate comparison: `research/benchmarks/results/micro-volume-activity-cohort-summary.json`
- Workflow and artifact provenance: `research/benchmarks/results/micro-volume-activity-cohort-provenance.json`
- Selection SHA-256: `303b752c0a18fc1677e89f825816e7a242a7230a1594712fa8640e29bed0cf42`
- Summary artifact: `9265392291`, digest `sha256:ac44a057fce3a423526db5405161dc9edcd3f6e9aadd495dba71fea783405355`

Corrected armed-time rerun:

- Selection: `research/benchmarks/results/micro-volume-activity-cohort-armed-time-selection.json`
- Aggregate comparison: `research/benchmarks/results/micro-volume-activity-cohort-armed-time-summary.json`
- Workflow and artifact provenance: `research/benchmarks/results/micro-volume-activity-cohort-armed-time-provenance.json`
- Selection content SHA-256: `a95a2cd852370837e41f52ae34b19487924277d8279f80f7fdfc3bc46b33c679`
- Summary content SHA-256: `80a22f213b5a1661c59e779cafff5b2af9507726898203ae3752e6d1738e75a6`
- Summary artifact: `9273840004`, digest `sha256:4139fbcb0cb0e66a70b9b5c29a28798df1677bd21a791c384d4a6667da21e0e1`

Separate completed-bar market-discovery rerun:

- Selection: `research/benchmarks/results/micro-volume-activity-cohort-completed-bar-selection.json`
- Aggregate comparison: `research/benchmarks/results/micro-volume-activity-cohort-completed-bar-summary.json`
- Workflow and artifact provenance: `research/benchmarks/results/micro-volume-activity-cohort-completed-bar-provenance.json`
- Selection content SHA-256: `904f85d6226121e7a37973899846580c0de3aa698c4d72f2c137762f55aaab87`
- Summary content SHA-256: `89765a59efd1fdaf85b2faaa5bc697f470f14475d219df0142fb445a1f3c7329`
- Summary artifact: `9274527606`, digest `sha256:c85c107b62e76232088b8fac888be8eed6f7d5df225cd76ec950794f368612d8`
