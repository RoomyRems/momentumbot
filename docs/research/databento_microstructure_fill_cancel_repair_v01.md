# Databento Fill/Cancel identity repair v0.1

## Purpose

This child records the verified EQPT Fill/Cancel classifier result and registers the smallest parser repair supported by that aggregate evidence. It changes only how a Databento `F` marker is associated with the `C` record that removes resting quantity inside one completed per-instrument event. It does not change event grouping, feature mechanics, windows, thresholds, strategy, broker behavior, or runtime authority.

The permanent classifier-success audit content SHA-256 is `a1a4b72301f78b6c06811d810a15ecd830559d5db52dc9187ae00d8973fc983f`. The unarmed repair registration content SHA-256 is `a5e8e0381e893610b641ce9a41d31138c1bde2134614efe7ebce725383b6abf0`.

## Verified aggregate evidence

GitHub Actions run `32512602607`, attempt 1, made one authorized EQPT MBO request and completed successfully. Its sanitized classifier reported:

- 29,159 instrument events;
- 1,020 Fill-bearing events;
- 1,346 Fill records and 1,382 Cancel records within Fill-bearing events;
- 1,331 Fill records in 1,007 events matched under the frozen five-field identity `(sequence, order_id, side, price, size)`;
- all 1,346 Fill records in all 1,020 events matched under `(order_id, side)`.

Therefore 15 Fill records across 13 events require the coarse identity. Dropping sequence and/or size did not increase overlap. Dropping price did. Within the preregistered projection lattice, price is the remaining differentiating dimension. This is an inference from aggregate counts; the diagnostic intentionally persisted no raw price, size, order-ID, or feature values and does not establish why the venue-normalized fields differ.

## Registered repair

For each completed `F_LAST` event scoped by `(publisher_id, instrument_id)`:

1. Collect Fill markers and Cancel records as multisets.
2. Maximize matches under the existing five-field identity so every previously valid event remains unchanged.
3. Match remaining Fill markers to remaining Cancels by `(order_id, side)` in stable record order.
4. Ignore the matched `F` marker for book state.
5. Emit the matched `C` record as canonical `DepthAction.FILL`, using the Cancel record's own sequence, price, size, order ID, side, and timestamps.
6. Leave unmatched extra Cancel records as canonical Cancels.
7. Fail closed with `fill_cancel_unmatched` if any Fill marker lacks a Cancel with the same order ID and side.

This preserves counts and avoids inventing a price or size. Exact events remain identical to v0.3; the repair is only a strict extension for coarse-only matches.

## Databento schema basis

Databento defines `F` as a resting-order Fill marker that does not itself affect book state, while `C` cancels or removes resting quantity. It defines `F_LAST` as the last record in one event for an instrument. Its XNAS normalization table shows Order Executed messages normalized into Trade, Fill, then Cancel records, and its order-book example applies Cancels to book state while ignoring Fill markers.

Official references:

- [Common fields, enums, and flags](https://databento.com/docs/standards-and-conventions/common-fields-enums-types)
- [Market by order schema](https://databento.com/docs/schemas-and-data-formats/mbo)
- [Venue and dataset normalization](https://databento.com/docs/venues-and-datasets)
- [Limit order book example](https://databento.com/docs/examples/order-book/limit-order-book)

## Current status: unarmed

No execution-authorization file, provider runner, or workflow was added. This change cannot call Databento or spend credit. It also is not wired into the paper or live order path.

A future EQPT repaired feature replay must be separately registered and explicitly authorized after this exact parent is published. That later run must remain aggregate-only, first-attempt-only, no-retry, and hard-budgeted before any download.

## Claim boundary

The aggregate classifier supports a parser identity repair. It does not prove predictive value, select a threshold, establish realistic fills, reconstruct consolidated national Level 2, model Ross Cameron's discretion, or establish profitability. Policy promotion remains a separate decision after representative out-of-sample and prospective paper evidence.

## Files

- Success audit: `research/data-audits/databento-microstructure-fill-cancel-classifier-v0.1-run-32512602607-success-2026-08-21.json`
- Repair registration: `research/strategy/databento-microstructure-fill-cancel-repair-v0.1.json`
- Unarmed mechanics: `src/momentumbot/research/databento_fill_cancel_repair_v01.py`
- Deterministic tests: `tests/test_databento_fill_cancel_repair_v01.py`
