# Sealed historical Micro runtime v0.1

## Frozen causal child

This provider-free child composes the independently verified final v0.13
source Snapshot, the already frozen v0.2 scanner activation plan, the complete
v0.1 SIP-print/prior-warmup capture, and the complete v0.2 raw-session-minute
supplement. It preserves the exact 30 dates, 192 first-qualification/profile-
union activations across 170 symbol/date pairs, both strategy profiles, and the
unchanged Micro-v0.1 fingerprint.

The child calls the existing `completed_bar_support_series`,
`aggregate_trade_bars`, and `build_micro_trigger_decisions` implementations.
It does not substitute one-minute bars for ten-second bars, manufacture missing
inputs, alter thresholds, or reinterpret unavailable inputs as no triggers.

## Causal price-basis adapter

The prior EMA-warmup capture is split-adjusted while the frozen intraday source
and raw-session supplement are on the raw price basis. For each symbol/date,
the adapter derives a single mechanical raw-to-split factor from only the
paired frozen raw and split minute closes whose bars completed no later than
the earliest activation. It uses the median ratio and fails closed if the
pairs are missing, nonpositive, or not mechanically stable. Prices and warmup
VWAP are converted; volume is unchanged. The factor, complete ordered-pair
commitment, pair count, last availability time, and maximum deviation are
sealed in each date result. Later session bars never influence the factor.

Raw-session timestamps, closes, and volumes must match the v0.13 source
exactly. The existing completed-bar rule excludes the retained 09:59 tail
whose bar ends at 10:00. Warmup contributes to EMA history but not session
VWAP. SIP prints retain their original nanosecond chronology and are aggregated
by the unchanged ten-second bar builder.

## Output and boundary

The write-once result contains one sealed file for each date plus a root
manifest. Every activation receives an explicit `triggered` or `no_trigger`
outcome, every decision retains its activation and eligible-profile identity,
and every input group has a causal content commitment. A deep output validator
checks the exact file inventory, date-plan equality, evidence hashes,
activation/decision coverage, aggregate counts, input artifact bindings, and
all negative boundaries.

The runtime has no provider or credential entrypoint. It cannot read
retrospective labels or transcripts, access Databento, simulate accounts,
fills, exits, or orders, execute a backtest, or promote policy. Its registered
next gate is candidate-bound execution and status input registration; that
gate must preserve these frozen Micro decisions and supply missing data rather
than infer results.

## Executed result

The provider-free child executed once on 2026-09-06 after both captures passed
independent verification. Its 31 files cover all 30 dates and all 192 frozen
activations. Forty-eight activations triggered 109 unique causal Micro
decisions; 144 have explicit no-trigger outcomes and zero are unavailable.
The profile membership totals remain 164 general and 55 small-account
activations; decisions carry 99 general and 25 small-account memberships.

The manifest content/file commitments are
`cca8dbf0fcf37dd05dc77355de06bf384f37c081152302ce750c939550100904`
and `2f46191a7a0e6ff085c58d589857b65617e33ae00ff9de018565ee8803d2e7cf`.
The complete relative-path/file-hash inventory commitment is
`06b285120bab6acd21836a02b44969b1128dcc182ab7ea0ee444dc4384608f03`.
All 170 causal basis records passed; the largest relative pair deviation was
`0.0004911591355597489`. The deep output validator passed, as did 44 focused
tests normally and under optimized Python and all 1,437 repository tests.
Provider calls, unavailable substitutions, retrospective access, account/fill
simulation, and backtesting remained zero.
