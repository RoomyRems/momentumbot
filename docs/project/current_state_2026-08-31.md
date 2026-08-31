# MomentumBot checkpoint — 2026-08-31

## Current state

The prospective August 24–September 4 panel is terminally closed. Its five
attempted dates were operationally incomplete, the five remaining dates were
withdrawn before starting, and the public default-branch workflows are now
validation-only. The exact closure record is
`research/data-audits/prospective-panel-v0.1-closure-2026-08-31.json`.

The replacement `sealed-historical-walk-forward-v0.1` experiment is registered
provider-free against research parent `a2d2ffe`. It freezes an opaque eight-part,
2,292-record transcript commitment, a 66-date prior-research exclusion manifest,
and a deterministic 30-full-session block. Runtime has not started, transcript
record values have not been decoded for selection, and no provider authority is
granted by the registration.

## Active gate

Provider availability passed after the v0.2 Alpaca credential-routing repair.
The exact v0.1 source acquisition was then consumed by GitHub Actions run
`33350635957` and failed safely at its registered 20,000-HTTP-attempt ceiling;
the next Alpaca request was blocked before network access. No final source
bundle was uploaded and v0.1 cannot be rerun.

The active repair is `sealed-historical-source-acquisition-v0.2`. It preserves
the 30 dates and the entire causal acquisition graph and changes only the
zero-incremental-cost shared HTTP ceiling from 20,000 to 40,000. It remains
provider-free until its exact registration is published and validated, and it
may run only once after consumption of its distinct child authorization.

The strategy scope freeze remains active: no new setup, AI authority, scanner or
Micro threshold change, account rule change, execution-cell selection, or
management-rule change is allowed inside this experiment.
