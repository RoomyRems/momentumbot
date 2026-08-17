# Micro v0.1 seed benchmark results

Status: **completed frozen-baseline seed evaluation**.

> **Source correction (2026-08-17):** the old ~$5.25 ARTL trade label belongs to an earlier NCO/ONCO discussion in the source transcript. ARTL is retired from scoring. Historical runtime data remains intact; the current four-case broad diagnostic is **8/10 = 0.8**, not 8/12. See `docs/research/artl_source_label_correction.md`.

This document records the first leakage-safe multi-example evaluation of the frozen deterministic `micro-v0.1` policy. It is intentionally a behavioral research result, not a profitability estimate and not a fitted strategy revision.

## Authoritative provenance

- GitHub Actions run: `31925087895`
- Runtime commit: `37b8f45f13e6e2f0159c9d307a2a14333d237ab8`
- Frozen policy ID: `micro-v0.1`
- Frozen policy fingerprint: `49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa`
- Runtime knowledge policy: `runtime_market_data_only_no_retrospective_labels`
- Benchmark knowledge policy: `ground_truth_label_only_never_runtime_context`
- Replay window: causal target qualification through the strategy's 10:00 ET no-new-entry cutoff.

The runtime replay is produced before retrospective benchmark labels are loaded. The human entry, outcome, pullback ordinal and reported P&L are therefore unavailable to Micro v0.1 during replay.

## What this seed benchmark tests

The four valid primary cases test whether a single frozen chart-only micro policy can causally recognize and participate in the same broad setup family across different historical examples. The benchmark does **not** yet claim to reconstruct the full historical cross-sectional stock-selection universe. For this micro-layer experiment, the known historical symbol/date is used only to reconstruct that target's causal price/gain/RVOL qualification and subsequent SIP tape.

`setup_detected` and `entry_participation` are deliberately broad dimensions. A later plan or fill on the same ticker can satisfy them even when it is clearly not the same human trade. Exact human trade identity is therefore **not** assigned an aggregate score.

## Authoritative seed result

The historical post-replay summary contained 12 comparable dimensions because it included the now-invalid ARTL labels. Excluding those two dimensions leaves 10 comparable broad behavior dimensions, of which 8 match: `8 / 10 = 0.8`. That number must **not** be described as imitation accuracy. The exact-human-trade aggregate score is intentionally `null`.

| Case | Causal qualification | Human reference | First Micro v0.1 fill | Broad result | Exact-trade evidence |
| --- | --- | --- | --- | --- | --- |
| **DSY 2026-06-10** | 07:42:00.017 ET | ~$3.07 / $3.11 | $8.50 at 07:53:00.393 ET, pullback #10 | setup + participation match | Strong mismatch: much later and ~$5.39-$5.43 above reported fills |
| **TIVC 2025-04-03** | 07:00:00.081 ET | $4.73 / $4.76 / $4.89; first pullback | $5.10 at 07:18:02.796 ET, pullback #7 | setup + participation match; first-pullback + ordinal fail | Wrong pullback identity despite relatively close price |
| **UPXI 2025-04-21** | 08:02:42.541 ET | ~$2.84 first-new-high entry | $7.23 at 08:37:31.468 ET, pullback #8 | setup + participation match | Strong mismatch: much later and $4.39 above reported entry |
| **MMA 2025-09-09** | 07:30:20.096 ET | ~$2.40 | $4.02 at 07:33:32.259 ET, pullback #3 | setup + participation match | Same family, but later pullback and $1.62 above reported entry |

The broad result therefore says: **Micro v0.1 often finds some later chart-confirmed micro behavior on stocks Ross traded, but it does not yet reproduce the specific early pullbacks he actually chose.**

## Case diagnostics

### DSY

Micro v0.1 generated two plans and one fill, but the first fill was pullback #10 at $8.50 rather than the reported ~$3.07/$3.11 trade. The runtime rejected 709 evaluation points as `no_current_running_high_pullback`, versus 38 `micro_retrace_above_half`, 11 `micro_pullback_volume_not_lower`, and 7 `no_micro_pullback_pause`.

The important structural observation is that Ross's local impulse/pullback around the reported trade does not need to be a new strict session-running high, while v0.1 requires exactly that. An earlier higher print prevents the local impulse from becoming the peak used by the frozen detector.

### TIVC

Micro v0.1 generated three plans and one fill at $5.10 on pullback #7. The benchmark explicitly labels Ross's first micro pullback as taken, with fills at $4.73/$4.76/$4.89, so both `first_pullback_taken` and `pullback_ordinal` fail even though the broad setup/participation dimensions pass.

The runtime recorded 929 `no_current_running_high_pullback` evaluations. Around the human trade, a red/pullback candle can make a marginally higher intrabar high. The frozen strict-running-high translation re-anchors on that print; the human interpretation appears able to continue treating the candle as part of the pullback.

### UPXI

The causal target qualifies at 08:02:42.541 ET, immediately before the very fast early move described in the recap. Micro v0.1 eventually produces four fills, first at $7.23 on pullback #8, versus the human ~$2.84 first-new-high entry.

This exposes a separate implementation boundary: the current evaluator discards structural micro history before `candidate_qualified_at`. Ross, however, can see the already-formed chart when a scanner alert appears. Resetting the entire structural state at the qualification instant can leave too little completed history to identify an immediate pullback causally.

### MMA

Micro v0.1 qualifies at 07:30:20.096 ET and fills at $4.02 on pullback #3 at 07:33:32.259 ET, compared with the reported ~$2.40 early entry. It is the closest case in elapsed time after qualification, but it still shows that the baseline reaches the setup family later than the human trade.

The dominant runtime reason is again `no_current_running_high_pullback` (855 evaluations), with only nine `micro_retrace_above_half` and two pullback-volume rejections.

### Retired ARTL label

Independent market research correctly identified ARTL as the March 27 session leader that matched the video's $3-to-$12.45 path. The later full transcript nevertheless proves that the approximately $5.25 losing ten-second trade was on the earlier NCO/ONCO stock, not ARTL. Ross reports his first ARTL trade separately at approximately $6.34. Because the ARTL chart timeframe and pullback ordinal are unresolved, ARTL is excluded from Micro scoring rather than relabeled with invented precision.

The ARTL runtime remains useful as a label-blind reconstruction, but its old human-entry comparison and upstream-timing conclusion are invalid. See `docs/research/artl_source_label_correction.md`.

## Cross-case finding: the current peak definition is probably too restrictive

Across the four valid primary cases, `no_current_running_high_pullback` is overwhelmingly the most frequent rejection reason. The count is an evaluation-loop diagnostic rather than a probability, but its consistency matters:

- DSY: 709
- TIVC: 929
- UPXI: 648
- MMA: 855

The strongest current hypothesis is that **"strict running high since qualification" is a machine translation, not an adequate representation of the human concept of a local momentum impulse followed by a micro pullback**. The transcript methodology supports a fast extension, controlled pullback/pause and first-candle-new-high entry; it does not require every eligible micro impulse to be a new session-running high.

## Second finding: qualification should gate action, not necessarily erase causal chart context

Micro v0.1 currently begins structural pattern history at the candidate qualification instant. This is causal but unnecessarily restrictive: all completed bars before the alert already existed and were visible. A future policy can use a bounded amount of pre-qualification completed chart history while still prohibiting any plan from being armed or filled before qualification.

This distinction is especially relevant to UPXI and MMA, where the human setup occurs very soon after the causal scanner gate becomes available.

## What must remain frozen

None of these observations modify `micro-v0.1`. Its current five-bar impulse translation, strict running-high peak, support tests, volume test and first-new-high trigger remain immutable under fingerprint `49c27b4a...62618fa`.

A benchmark mismatch is evidence for a separately named hypothesis. It is not permission to rewrite the baseline after observing the answer.

## Recommended v0.2 ablation order

The next research step should isolate causes rather than combine fixes immediately:

1. **Pre-qualification structural context ablation.** Permit a bounded window of completed 10-second bars from before qualification to define the first post-qualification setup, while action remains prohibited before qualification. This corrects an information-boundary translation without weakening geometry.
2. **Local-impulse peak ablation.** Replace the strict session-running-high requirement with a causal local impulse peak definition, then compare against exactly the same frozen cases.
3. **Combined context + local-peak ablation.** Only after the first two effects are measured independently.
4. Keep whole-dollar/half-dollar, Level-2/tape anticipation and exit/campaign logic separate; they address different layers and should not be smuggled into the chart-only micro baseline.

The seed suite should remain a diagnostic set rather than an optimization target. Any promoted v0.2 rule should subsequently be checked on additional transcript-labeled cases and broader walk-forward days that were not used to select the rule.
