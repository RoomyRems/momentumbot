# Historical setup, stop and source audit v0.1

This additive diagnostic starts from `a27babed52e1c2a12151be40af36a7c865f395f9`,
tree `67f32e01b56d874f278b86c2e0ca6bb45ef865f9`. Its single question is whether
the existing entries and stops reproduce from their original causal Micro
inputs, and which explicit setup and source characteristics those entries have.
The conditional baseline's losses and the earlier GITS ordinal-5 example were
already known when this scope was specified. This is a post-result diagnostic,
not an unseen-data policy experiment or a causal estimate of a changed rule.

The frozen loss-attribution registration is
`0a6153ad10b3a97ff13252db6176bdf01bf4c25474a2ee38bec8d5b5b49487ff`; its report is
`5487f89ae0002b276aee2c051446a862d58ec0afb1ec4c0a6b3fa16b5ff3a7d3`.
All 109 original opportunities, 744 path references, 12 account alternatives,
360 session slots, 30 selected dates, and original unavailable history remain.

Before computing new findings, the diagnostic is limited to these observations:

- Reconstruct each already-selected plan's exact committed causal prefix from
  the original SIP/warmup, raw-minute and scanner archives; require equality
  with its original `micro_runtime_content_sha256`.
- Re-evaluate the unchanged geometry and compare its plan, stop, pullback
  ordinal, completed-bar availability, and first eligible trigger print with
  the original decision. Verify raw/split basis and raw-session alignment.
- Record pullback ordinal, duration, retrace, volume contraction, peak wick,
  support, trigger/stop distance, room to the original peak, and completed-minute
  MACD as descriptive fields. These fields do not add an entry filter.
- Bind original entry quotes and confirmed fills to those source plans. Report
  quote age, spread, stop distance, and SIP-trigger versus single-venue quote
  price/time differences without inferring consolidated quotes or a new fill.
- Summarize fixed outcomes by exact original ordinal and recorded exit reason.
  Preserve every alternative and original decision. No dropped-entry return,
  best threshold, stop widening, or policy-promotion claim is permitted.

Only retained original market inputs and saved runtime/accounting records may
enter this audit. Ross transcripts, recap labels, later prices as setup inputs,
new provider requests, account replays and brokerage activity are excluded.
Later fills and recorded exits are joined only after source reconstruction, for
descriptive accounting. Any reconstruction mismatch must remain an explicit
failure; the frozen source, original checker and baseline cannot be altered to
make it pass. A complete account replay is not part of this diagnostic.

## Reconstruction and saved verification

The new audit module and command do not call an account runner. They first
reproduce the parent loss report and verify the complete original source ZIP
identities, inventories, logical tape hashes, request bounds and raw/split
normalization. They select the 45 symbol/date pairs containing the original
109 opportunities; the other original activations remain in the frozen parent.
The earliest original symbol activation determines normalization even if that
activation did not produce an opportunity.

Trade aggregation uses column iteration to avoid replaying millions of pandas
rows through the slower original row iterator. It retains the original trade
condition rules, row ordering, equal-clock ordering, bucket arithmetic and
serialization. Synthetic parity checks compare both implementations exactly.
The decisive historical check is equality with every pre-existing causal-prefix
hash, including the original bar timestamps, support and eligible chart trades.
The unchanged Micro evaluator reconstructs each selected plan and stop.

Support is available only after minute completion, and the geometry uses support
available by the original trough bar start. Descriptive MACD uses completed
minutes available by the plan bar start and strictly prior normalized warmup.
The signed room measure compares the planned trigger with the original running
peak, divided by trigger-minus-stop risk. It is not a complete resistance map.
These fields are observations, not new entry requirements.

Saved compressed witnesses retain geometry, support and MACD for deterministic
verification without distributing the original trade archives. The saved
verifier re-evaluates plans/features, checks source identity and original quote
bindings, and rebuilds all ordinal cohorts and account-result joins. Full
chart-prefix authentication still requires the three exact original archives.
It does not establish consolidated quote quality, real fill calibration, a
causal policy effect or full market coverage.

The source-run contract is
`5f9adda53eba4f872aae040e20c30c1eae63122eb4e884d20db011b447fe0570`.
Reproduction takes explicit original archives and a new output directory:

```bash
PYTHONPATH=src:scripts python scripts/audit_sealed_historical_setups_stops_v01.py \
  --expected-contract-sha256 5f9adda53eba4f872aae040e20c30c1eae63122eb4e884d20db011b447fe0570 \
  --micro-zip /absolute/path/to/original-9995887799.zip \
  --minutes-zip /absolute/path/to/original-9995587996.zip \
  --scanner-zip /absolute/path/to/original-9993250947.zip \
  --output-directory /absolute/path/to/new-audit-directory
```

For the saved geometry and accounting check, supply the same contract hash with
`--verify-saved`. The command installs the existing offline I/O guard, denies
network/subprocess activity, and records an explicit failure if reconstruction
cannot complete.

## Findings

The first historical reconstruction completed successfully: all 109 original
causal-prefix hashes and plans match, and all 300 closed-episode entry stops
match the reconstructed source stops. The 45 source pairs contain 10,965,021
original SIP rows and span the 25 dates with opportunities. All 30 original
dates, including the five zero-Micro dates, remain in the account population.
This establishes reproduction of the current policy and source evidence. It
does not establish that the policy's setups or stop rule have a trading edge.

The 109 opportunities have five first pullbacks, 13 second pullbacks and 91
third-or-later pullbacks; the largest recorded ordinal is 27. The Micro-v0.1
evaluator has no ordinal cap. It enforces its existing retrace, pullback-length,
volume, wick and support conditions but installs neither a MACD gate nor a
minimum room-to-peak gate.

At the planned trigger, 101/109 opportunities have less than 2R of room to the
original running peak. Four have nonpositive completed-minute MACD; none has
unknown MACD. Room to that peak is only a geometric measure: it does not assert
that the peak is an impassable resistance level or that continuation beyond it
is unavailable. These observations must not be turned into improved-return
claims by deleting inspected entries.

Each row below applies separately to the unchanged 1-, 5- and 10-second
alternatives. Counts are closed entry episodes within each path, including the
original re-entries; they are not independent observations across horizons.

| Account / execution | Episodes | Net P&L | First-pullback cohort net | Second-pullback cohort net | Room below 2R | MACD nonpositive |
|---|---:|---:|---:|---:|---:|---:|
| Main / conservative | 42 | −$264.77 | −$96.13 (3) | −$83.76 (8) | 40 | 1 |
| Main / stress | 31 | −$239.78 | −$64.74 (2) | −$7.23 (6) | 29 | 1 |
| Small / conservative | 15 | −$35.75 | −$8.09 (3) | −$19.05 (5) | 13 | 1 |
| Small / stress | 12 | −$13.75 | −$5.95 (2) | −$8.29 (3) | 11 | 1 |

First and second pullback cohorts are both negative in each combination. These
are the saved fills' cohort totals, not a replay of an account that only trades
those cohorts: filtering could change capacity, campaign order and later fills.
The complete report retains every exact ordinal without selecting a threshold.

The 86 original decision references satisfy their original inclusive 100 ms
lookback. Quote age ranges from 7,675 ns to 78,476,739 ns, with median 2,822,633
ns. Spreads range from $0.01 to $1.47, with median $0.04. The quote's ask differs
from its SIP trigger print by −$0.46 to +$0.21, with median zero. In two of the
86 references the spread is at least the ask-to-stop distance. These checks
preserve SIP exchange time and XNAS receive time as distinct clocks and do not
calibrate cross-venue fills or establish that quote differences caused losses.
All 23 unavailable opportunities and 162 unavailable path references remain.

The result supports a separate preregistered setup-selection experiment, with
an evaluation sample and selection rules fixed before its outcomes are opened.
It does not justify changing stops, selecting a profitable ordinal cutoff,
promoting a policy, or requesting another full local account replay.

Report content commitment:
`40c716fa69e99944ddfe8f168d4697d0bc4b6db1a0491f0f4e0f70f54536a39b`.
Saved geometry commitment:
`5b326b3921b58456b7f77cf3b5fc753aa8f04946efb6cad4eab150331ac15bd1`.
See the [complete report](../../research/data-audits/sealed-historical-setup-stop-audit-v0.1/report.md),
[machine-readable evidence](../../research/data-audits/sealed-historical-setup-stop-audit-v0.1/report.json)
and [implementation verification](../../research/data-audits/sealed-historical-setup-stop-audit-v0.1/implementation-verification.json).

## Validation and retained history

All 22 focused tests and all 2,473 full-suite tests passed with zero skips.
The full suite took 286.362 seconds on Python 3.12.14 with the retained native
SDK dependencies; no packages were downloaded. Compilation and the saved-evidence
command with Python assertions disabled also passed. All seven publication
workflows for the frozen parent were verified successful.

Before registration, synthetic parity testing caught an empty-chart formatting
difference in the new helper. The helper now delegates empty inputs to the
unchanged original function; all 16 synthetic tests passed before the historical
source run began. Both development logs are retained. The first historical
source reconstruction succeeded. Its complete progress log, the focused test
log, the saved-verification log and the compressed full-suite log are preserved
alongside the implementation verification. No failed historical experiment or
unavailable original observation was removed or reclassified.
