# Databento instrument-event grouping repair v0.3

## Purpose

The authorized v0.2 safe classifier completed one INTJ MBO request and
localized the prior ambiguous `ValueError` to
`atomic_key_change_before_last`. The frozen v0.1 adapter required
`publisher_id`, `instrument_id`, and `sequence` to remain identical from the
first pending record through `F_LAST`. The real stream changed that key before
the boundary, so no canonical event or feature snapshot was retained.

The independently verified observation is permanently recorded in
`research/data-audits/databento-microstructure-feature-diagnostic-v0.2-run-32478204001-failure-2026-08-21.json`.
It binds workflow run `32478204001`, attempt 1, the exact commit and tree, the
sanitized artifact and all recomputed hashes, one request, no retry, the
`$0.000130802393` quote, and `117,040` billable bytes. Actual billing remains
unknown.

## Corrective hypothesis

Databento defines `F_LAST` as the last record in an event for a given
`instrument_id`; the book should be inspected only after that flag. For Nasdaq
TotalView, normalized records from the same native message share the venue
sequence number. Those statements do not require every pending record since a
prior instrument boundary to have one sequence value.

The v0.3 repair therefore:

1. buffers pending records independently by `(publisher_id, instrument_id)`;
2. closes only that scope when one of its records carries `F_LAST`;
3. preserves original record order and every venue sequence value;
4. restricts XNAS Fill-to-Cancel conversion to the same sequence, order ID,
   side, price, and size;
5. routes every scope to its own pair of deterministic feature engines; and
6. fails closed if any scope remains incomplete at end of stream.

The frozen v0.1 adapter, v0.2 classifier, and threshold-free feature engine are
unchanged. The repair changes no feature window, threshold, strategy rule,
scanner, broker, account, or risk behavior.

Official semantics:

- <https://databento.com/docs/standards-and-conventions/common-fields-enums-types>
- <https://databento.com/docs/examples/order-book/order-tracking>
- <https://databento.com/docs/venues-and-datasets/xnas-itch>

## Deterministic verification

The focused suite proves that:

- a sequence transition before `F_LAST` is accepted within one instrument
  event;
- interleaved instruments close independently and never share a feature
  engine;
- Fill and Cancel records cannot match across sequence values;
- an incomplete scope still fails closed when another scope completes;
- every metric from the previously valid frozen v0.1 fixture is identical;
- mixed-sequence replay remains deterministic and threshold-free;
- budget rejection makes zero time-series calls;
- provider failures remain sanitized and never retry; and
- loading or publishing the unarmed bundle cannot import the Databento SDK or
  trigger its workflow.

Synthetic verification is necessary but not proof that the exact real INTJ
stream will replay. That requires a later, separately authorized one-shot
request.

## Unarmed publication gate

The v0.3 workflow listens only for a future file that is intentionally absent:

`research/strategy/databento-microstructure-feature-diagnostic-v0.3-execution.json`

Publishing the code-only registration cannot call Databento. A future
authorization must be the sole file in a direct-child commit, bind the exact
published parent SHA, permit exactly one first attempt, and retain the hard
ceilings of `$0.001` and `1,000,000` billable bytes. The workflow does not
support manual dispatch or automatic retry and cannot call MBP-10, batch, or
live endpoints.

## Interpretation boundary

Even a successful future replay would establish only that this classified
parser defect was repaired. It would not establish predictive value,
Ross-equivalent discretion, consolidated Level 2 coverage, calibrated fills,
or profitability. Policy promotion remains prohibited until preregistered
held-out evaluation, execution calibration, and prospective paper evidence
support it.
