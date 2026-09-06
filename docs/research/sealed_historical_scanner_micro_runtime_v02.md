# Sealed historical scanner/Micro runtime v0.2 preparation

## Bound source

This unarmed child is bound to final v0.13 source-freeze run `34039993297`,
attempt 1, artifact `9993250947`. Its measured ZIP SHA-256 is
`af89836213a905a1e02dabd54cce1d2bab2f55214c2d7bc0dce44d4700243638`,
the recovery report file/content hashes are `048644a52d368381de3d01c143255758dd90f47b800d94716c4baa3193fcbdbf`
and `03d2853fd82163387ee55fa32ba50c5f18e2c7a8a96e80054ff9830d47bd43c4`,
and the complete 767-file source tree is
`74cc2895bf46d1c9a054f57108b7aae17af6a291f72678f1cd935118c844bed6`.

All 30 registered dates, both strategy profiles, and Micro-v0.1 remain
unchanged. This registration authorizes no execution, provider call,
credential use, retrospective-label access, backtest, account access, or
order.

## Mechanical next stage

The next separately authorized provider-free command may reapply
`current-general-2026` and `current-small-account-2026` to the frozen causal
scanner rows. It must retain the first qualifying minute per symbol/profile,
union exact-time profile ties, and freeze a write-once activation manifest.
That manifest may define the exact candidate-bound Micro input request set. It
must stop before a provider quote, download, Micro replay, account replay, or
retrospective comparison.

## Required fail-closed dependency

The v0.13 source bundle contains causal raw/split one-minute scanner inputs and
all 30 frozen scanner snapshots. It does not contain completed 10-second bars
or normalized SIP trade events. Both are required by unchanged Micro-v0.1.
One-minute bars may not be subdivided, interpolated, or substituted, and
absence of the required inputs may not be reported as zero Micro triggers.

After the exact activation/request manifest is frozen, any quote or acquisition
of candidate-bound Micro inputs requires another bounded authorization. Only a
complete, hash-bound input artifact can unlock the later label-blind Micro
runtime. Backtesting and retrospective labels remain later gates.

## Validation and review handoff

The existing isolated preparation was reconciled before this review, then
hardened to reject rehashed contract or registration changes, deny network and
child-process I/O using the existing v0.13 guard, and reject output paths inside
the immutable source artifact (including symlink aliases). The CLI distinguishes
source validation from scanner materialization and never claims Micro execution.

Preparation and complete source validation use this provider-free command:

```sh
PYTHONPATH=src python scripts/prepare_sealed_historical_scanner_micro_runtime_v02.py \
  --snapshot-root /path/to/verified-final-artifact
```

It verifies the exact final report, intermediate checkpoint, and every source
file before reporting scanner readiness and the explicit Micro dependency gap.
Its default mode only validates the frozen contract and registration.

After separate authorization tied to the reviewed preparation commit, the same
command may add `--materialize-scanner-activations /path/to/new-output` to write
the 30-date scanner activation and Micro input plan. The output must be empty
or absent and outside the source artifact. This materialization has not been
executed on the actual historical panel during preparation. It cannot quote or
fetch providers, run Micro, simulate fills or accounts, or open retrospective
labels. `runtime_execution_authorized=false` describes the authority granted by
the registration; any future execution needs separate user authorization.

Verification results and test receipts accompany the source-freeze audit at
`research/data-audits/sealed-historical-source-v0.13-final-verification-34039993297.json`.
The preparation remains local; the installed `main` dispatcher and all remote
refs are unchanged, and no workflow was launched for this preparation.
