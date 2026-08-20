# Databento microstructure smoke acquisition v0.1

This child advances the frozen Level 2 feasibility study from a free metadata
quote to one bounded historical acquisition. It does not tune or promote a
strategy.

## Frozen scope and budget

The source cohort and four smoke cases remain unchanged: INTJ and EQPT on July
10, AMC on July 20, and GMM on July 10. For each case the runner requests the
same five exact schemas and windows that passed the metadata quote: MBO,
MBP-10, trades, definition, and status.

The independently verified quote was $0.207468646765 for 379,772,560 billable
bytes. Immediately before acquisition, the workflow repeats all 20 free cost
and size queries. It downloads nothing if the conservative total exceeds $0.50
or 500,000,000 bytes. There is no batch job, live subscription, broad-history
request, or automatic retry. It accepts only the first Actions attempt of the
direct push from published branch head
`cfe6b00692feea250856afef7a3e1164f178a6e6`; a later push or job rerun cannot
repeat the paid requests. Once acquisition begins, the first provider, file,
or parser failure stops the remaining requests because completed requests may
already be billable. A completed integrity comparison is evaluated after all
exact files finish, so a mismatch cannot conceal the other schema evidence.

## Data handling

Licensed DBN files exist only in a temporary runner directory. They are parsed
there, hashed, deleted, and never committed or uploaded as GitHub artifacts.
The retained report contains only non-reconstructable counts, booleans, quoted
cost and byte totals, and file SHA-256 values. It contains no raw record,
price, size, order ID, point-in-time instrument mapping, credential, provider
exception text, or temporary path.

This is a deliberate child-level refinement of the provider-neutral parent:
the public repository can bind evidence to raw data by cryptographic digest,
but it cannot redistribute the vendor data itself.

## Reconstruction check

MBO is replayed from the provider's synthetic start-of-day snapshot. Book state
is inspected only after a non-snapshot event closes with `F_LAST`. Two separate
in-memory implementations run over the same events:

1. an incremental order-and-price-level book; and
2. an independent order map that aggregates levels only at a sample.

MBP-10 supplies a third, provider-derived reference. For each publisher and
instrument, the last MBP-10 record by receive time in each UTC minute is chosen
mechanically. At the matching MBO `F_LAST` venue sequence, the two local books
must agree with one another and with all ten MBP-10 price, size, and order-count
levels.

Trade and Fill records do not mutate the book because Databento documents that
their accompanying cancels carry the book change. Snapshot, top-of-book,
undefined-price, clear, add, cancel, modify, and `F_LAST` semantics follow the
provider's published MBO examples.

## Stop/go interpretation

G1 passes only if all exact files complete, required event schemas are
nonempty, every MBO case contains a snapshot clear, metadata matches the
request, and parsing/cleanup succeeds. A status file may legitimately contain
zero records when no status transition occurred.

G2 passes only if every case has an aligned sample, at least 95% of its
mechanical MBP-10 samples align by sequence, both independent local replays
match, MBP-10 matches exactly, and no invalid event, orphan mutation, timestamp
inversion, sequence reversal, or crossed sampled book remains.

Failure is useful evidence and is preserved. Passing proves only that this
single-venue data can support causal engineering mechanics. It does not prove
profitability, model Ross Cameron's discretion, represent consolidated national
depth, or create any entry, exit, sizing, paper-order, or live-order authority.

Official implementation references:

- [Databento MBO schema](https://databento.com/docs/schemas-and-data-formats/mbo)
- [Databento MBP-10 schema](https://databento.com/docs/schemas-and-data-formats/mbp-10)
- [Databento MBO snapshots](https://databento.com/docs/standards-and-conventions/mbo-snapshot)
- [Databento order tracking](https://databento.com/docs/examples/order-book/order-tracking)
- [Databento limit-order-book construction](https://databento.com/docs/examples/order-book/limit-order-book)
