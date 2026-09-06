# Historical execution/status acquisition v0.1

This child binds independently verified quote run `34066187628`, result artifact
`9999061044`, and research checkpoint `20c500723b9062479191419a406d155c94b3ef6c`.
It tests whether the exact 90 candidate-bound requests can produce complete
minimal receive-time quote/status tapes without changing their windows,
symbols, schemas, venue, or the frozen execution semantics.

## Frozen inputs and ceilings

The 109 Micro decisions, 45 symbol/date pairs, all 30 dates, and five valid
no-decision sessions remain bound through the original request manifest. The
quote ZIP is `2a353b635407bffdb8076d88acdc520ad48f0bc19e28ff5d8c2e4ede8a88aa43`.
Its report file/content commitments are
`d2197b2c4319391f6f7164d414bfef9c8755a502069ecff410e1d6757ce45682` /
`d74deaf49f63410da1452d494306dd07e22eedf3f572e3171d7c2ded34d18374`.

Before any download, all 180 exact size/cost calls must complete again. Both
aggregate estimates must remain at or below 154,456,640 billable bytes and
USD `0.172787457709`. Missing, zero-size, failed, or increased aggregate quotes
block every time-series call. This is a new acquisition preflight under its own
consumption record; the original quote operation remains immutable.

A successful preflight permits exactly one `timeseries.get_range` per request,
in frozen order, with no retries or redirects. The first download or validation
failure stops later requests. The total ceiling is 270 HTTP attempts: 180
metadata and 90 time series. Per-request wire bytes are bounded by that
request's original billable-size quote plus 65,536 bytes for DBN metadata and
compression overhead. This transport allowance does not increase either
billable-byte or cost ceiling. Normalized tapes have a one-billion-byte retained
compressed ceiling and a 1.5-billion-byte decompressed ceiling.

## Causal normalization and retained evidence

The historical adapter reuses unchanged `_normalize_store`, `_quote_events`,
and `_status_events` mechanics from the prospective implementation. It checks
the exact dataset, schema, raw-symbol mapping, nanosecond start/end and every
required normalized field. Quote sequence/receive-time ordering and original
equal-time status order are preserved. Missing records fail closed. There is
no date-validator monkeypatch and no reinterpretation of prospective artifact
IDs as historical inputs.

Each request uses one temporary DBN file, whose completion hash is recorded and
whose bytes are deleted before the next request. Only the minimal normalized
fields persist as deterministic gzip JSONL tapes. Every completed tape has a
separate sealed receipt containing its request, row count, decompressed content
hash, file hash/size and ephemeral DBN commitment. A failure retains preceding
completed tapes, its exact request and phase, and sanitized ledgers; it cannot
produce a partial-success gate.

Separate metadata and time-series HTTP ledgers record attempts before I/O.
The final report and full file inventory retain all counts and provenance.
The credential exists only in the sole provider step and is never persisted;
provider response bodies and exception text are not diagnostic outputs.

## One-shot workflow and continuing gate

The code push runs offline validation only. After exact-parent CI and dedicated
normal/optimized validation pass, a sole added execution record can consume
one first-attempt research-branch push. The workflow verifies the original
quote run and artifact, downloads its exact ZIP and validates every member,
then atomically creates
`refs/tags/sealed-historical-execution-input-acquisition-v0.1-consumed`.
That marker and its supporting evidence must be durably uploaded before the
provider step. CPython 3.12.14 and the existing hash-locked Databento 0.83.0
environment remain pinned. Main and prior consumed refs are unchanged.

After capture, independently download the consumption and result ZIPs and
verify their measured GitHub digests, every archive member, all receipt/report
hashes and the complete decompressed tape contents. A successful acquisition
gate means the requested records are complete, not that every candidate has
usable execution quotes or known initial status. The next provider-free
historical capture composer must preserve the existing unavailable-status,
ambiguous-time and unusable-book rules. Account/fill simulation remains blocked
until those input gates and registered management inputs are satisfied. No
source or Micro rerun, policy change, retrospective input, order access, or
backtest is part of this acquisition.
