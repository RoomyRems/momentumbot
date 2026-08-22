# Databento microstructure behavioral cohort execution v0.1

This harness executes the already-frozen `microstructure-behavioral-cohort-v0.1`
without changing its opportunities, anchors, prospective quantities, request
surface, feature mechanics, comparison protocol, or authority boundary.

The checked-in harness is unarmed. Its workflow triggers only when the sole
future file
`research/strategy/microstructure-behavioral-cohort-v0.1-execution.json` is
published as the only change in a direct child of the harness checkpoint. The
runner also requires GitHub Actions attempt 1 and an exact match between the
push parent and the parent named in that authorization.

Before any timeseries request, the harness quotes all five frozen date-grouped
`XNAS.ITCH` MBO requests with `metadata.get_billable_size` and
`metadata.get_cost`. It downloads nothing unless all five quotes succeed and
their aggregate is no more than `$0.25` and `225,000,000` billable bytes. A
provider, mapping, replay, checkpoint, or comparison failure stops the run. It
does not retry and does not substitute a partial cohort.

Downloaded DBN files exist only in a temporary runner directory and are
deleted after their one replay. Provider symbology embedded in the DBN store is
used to map instrument IDs to the frozen raw symbols; no extra symbology API
request is made. Completed per-instrument events are grouped by their Databento
`F_LAST` boundary and translated under the frozen Fill/Cancel repair.

Each instrument stream is replayed through two independent copies of the
unchanged threshold-free feature engine. Snapshots are taken only at the exact
registered anchor and at the registered one-, five-, and ten-second endpoints.
An anchor inside an incomplete atomic event fails closed. Every comparison is
built by the frozen label-blind comparator using the opportunity's pre-existing
quantity and breakout level.

The uploaded artifact contains quote totals, byte totals, request and event
counts, aggregate availability/direction counts, and cryptographic comparison
digests. It contains no raw market records, raw DBN, order or instrument IDs,
feature snapshots, per-opportunity values, pre/post values, provider error
detail, Ross labels, retrospective outcomes, P&L, later prices, credentials,
thresholds, broker actions, or runtime authority. Any result remains
shadow-only research evidence and is not eligible for policy promotion.
