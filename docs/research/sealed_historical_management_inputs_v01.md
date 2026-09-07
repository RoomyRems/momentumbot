# Complete historical management inputs v0.1

## Frozen parent and hypothesis

This provider-free child binds audited capture checkpoint
`536226a134aa9863130205b954065f24c89ce599`, tree
`f0bc8b58e6c5988849b97717993390b42a1d19ce`.
The sole hypothesis is that the verified retained prefixes and ten exact
captured tails supply all frozen management-source envelopes. It does not
test, alter or promote a trading policy.

The three immutable sources are original SIP artifact `9995887799`, original
raw minute artifact `9995587996`, and missing-tail artifact `10026551595`.
Their complete file inventories and logical tape commitments are reverified
against the independent parent audits before any composition. No market-data
credential, provider call, acquisition child or new consumption tag is needed.
Ross transcripts, recap actions, retrospective labels and later outcomes remain
prohibited inputs. All prior captures and consumption references are immutable.

## Composition and lineage

All 56 merged windows receive a complete SIP trade tape and raw one-minute bar
tape: 112 resources, built from 122 adjacent, disjoint half-open segments.
The intended population is 3,654,215 SIP records and 975 raw minute bars.
Original canonical JSONL bytes are copied without rewriting or sorting; equal
timestamps retain their source order. Gzip uses level 9, zero mtime and no
embedded filename. Warmup data is not management input, and no trade-eligibility
filter runs at this stage.

Each compressed tape is finalized in memory before one exclusive file write,
flush and fsync. The original source archives remain streamed; no full-source
in-memory copy or provider reacquisition is needed.

Each resource receipt commits to the compressed file, logical rows and complete
source lineage. Contiguous segment spans map a composed ordinal back to the
original artifact, request and source ordinal. Source membership is independently
checked using timestamp intervals, not merely by trusting these ordinal spans.
Empty exhausted input remains empty evidence; it is not an inferred exit.

The final file inventory must match the write-time receipts. Every gzip stream
is read through EOF and checked for CRC, logical hash, newline count and row
population before the success manifest is written. This also runs on subsequent
verification and reader initialization.

The first local candidate was rejected by independent verification because five
final files differed from their write-time receipts. A second local candidate
was rejected by the strengthened pre-freeze check. Neither was published as a
verified result. Both evidence sets are retained. Receipt-to-final-file and
finalized single-write behavior have dedicated regression coverage; the cause
of the local streaming-write discrepancy is not established. No source capture
or runtime authority changed.

## Opportunity-bound access and remaining gates

`ManagementInputBundle` requires an externally pinned freeze-manifest content
hash and exact committed metadata. It returns original opportunity metadata
and clips records to that opportunity's own `[start_ns, end_ns)` interval. A
later opportunity's extended merged tail cannot enter an earlier opportunity's
input stream. Every returned record carries original and composed ordinals.

All 109 opportunity identities, 86 available and 23 unavailable entry inputs,
30 dates and five no-decision dates remain unchanged. Unavailable entry inputs
are not inferred no-trade outcomes. The $30,000/$2,000 once-only account seeds
and all 360 session dependencies remain untouched.

This input reader is not a causal management evaluator. In a later separately
registered projection, a minute bar must not be used before its close; trade
eligibility and the frozen `half-2r-breakeven-first-red-1m` mechanics must also
be applied there. Descriptive SIP exits cannot close an account position or
book an executable fill. Management/execution/account gates and portfolio
financial-metric eligibility remain false.

Next: register causal management projection and its executable-exit dependencies
against the verified complete bundle. Causal next-session valuation and
historical account replay remain later dependencies. No account replay,
backtest, provider purchase or brokerage access is authorized by this child.

## Reproduction and retention

Registration: `research/strategy/sealed-historical-management-inputs-v0.1.json`.
Five small metadata files live in
`research/runtime/sealed-historical-management-inputs-v0.1/`; the full bundle
is a retained GitHub Actions artifact, not a large Git data commit.

Use the hash-locked `requirements-sealed-execution-quote-v01.txt` environment.
The CLI installs the external-I/O denial hook before importing research code.

```bash
python scripts/build_sealed_historical_management_inputs_v01.py --validate-registration
python scripts/build_sealed_historical_management_inputs_v01.py --build --check-committed \
  --sip-zip /exact/original-sip.zip --bars-zip /exact/original-bars.zip \
  --tails-zip /exact/missing-tails.zip \
  --output-root artifacts/sealed-historical-management-inputs-v0.1
```

An existing output is never overwritten. `--verify` independently rebuilds
from all three original ZIPs in a temporary directory and requires an exact
match. `--freeze-metadata` is for the initial new build only, not an update
operation. Failed partial bundles remain evidence and cannot satisfy the
verified reader.

The hosted workflow uses read-only GitHub permissions to download only the
three pinned artifacts, then reconstructs offline and checks all five committed
metadata documents and all 112 tape hashes. It retains a complete bundle only
after successful verification, for 90 days. Source-artifact expiry is an
explicit retention dependency, not authority to reacquire market data.

## Verified result

Code `b616d60f48c8596fc31e6dc0d4943171fade18c6` passed all eight hosted
workflows on attempt 1. Local verification passed all 1,724 tests with zero
skips; 92 dedicated tests passed normally and optimized locally and hosted.
Generic CI passed with 51 optional-SDK skips. Static undefined-global checks
passed for both entry points.

The dedicated [reconstruction run](https://github.com/RoomyRems/momentumbot/actions/runs/34147224779)
rebuilt all sources and matched the frozen compressed bytes. The downloaded
artifact `10028253493` was independently checked against all 117 local files.
It is 43,591,721 ZIP bytes, SHA-256
`e6ae822301440e3c0d183546b472e5b6f4e0f50d6e4f1b67178ba6bf46e382e0`,
and expires on 2026-12-06. Unpacked bundle size is 43,991,068 bytes; the 112
tapes total 43,461,101 compressed bytes.

The frozen manifest content commitment is
`df00c1aa3e66fbb3040e63df210ef71ead7518858f5bc3ff44fc59067eeb15de`.
The independent checker verified all 1,064 original files, 520 logical tapes
and 20,106,693 logical source rows, then compared every one of the 3,655,190
composed rows with an independently timestamp-selected original record.
Both rejected candidates' truncated files are exact recorded-length prefixes
of the final verified tapes, preserving reproducible failure evidence without
misclassifying either candidate as a valid freeze.

The [permanent audit](../../research/data-audits/sealed-historical-management-inputs-v0.1-independent-verification.json)
retains both independent checkers, all output hashes, hosted evidence, source
commitments and the rejected-candidate metadata. Main and all prior consumed
references remain unchanged. The next gate remains causal management and
executable-exit registration, not account replay or financial evaluation.
