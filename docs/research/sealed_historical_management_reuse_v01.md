# Historical management source reuse v0.1

This provider-free child binds account-input commit
`cf729c27d3e458e4762ee1d60d48a6c57a25a5d8`, tree
`c3ca04d647c9f6126dd4b88601c011f46cc6825d`. Its one hypothesis is that the exact
retained SIP and raw-minute captures can supply the covered portions of the
already-frozen management windows without changing any source or policy.
Ross actions, transcripts, labels and account outcomes are excluded.

The approved $30,000 main / $2,000 small once-only seeds, all 12 account paths,
all 30 dates, all 109 opportunities, the 23 unavailable entry inputs and the
15-minute signal / 60-second observation windows remain bound to that parent.
This stage performs no account replay, entry/exit simulation or management
projection.

## Exact retained sources

| Source | Run | Artifact | Retained files | Tapes |
|---|---:|---:|---:|---:|
| SIP prints and prior warmup | 34053730042 | 9995887799 | 688 | 340 |
| Raw same-session minute bars | 34054580516 | 9995587996 | 348 | 170 |

The ZIP commitments are respectively
`d31eac851c1246ce23025e9518562ed3f41b8f818d42b8de707a6d86d307be99`
and `d689f493c10996bee7eddde68d62812e7850fc322caa2d530d33a97c84878e3f`.
Their immutable prior audits and 35 parent files are pinned in the registration.
The verifier checks both whole archives, every member, every original request
and receipt, both separate ledgers, and every uncompressed tape hash and row
count. Prior warmup is verified as retained evidence and is never a management
price source.

Coverage follows the complete, exhausted provider request envelope. It does not
follow the first or last observed print, assume a print in every interval or
invent bars for minutes without records. A zero-record selection remains an
explicit selection receipt; it does not establish a trade, exit or portfolio
outcome.

For rows inside a reusable management interval, the unchanged historical
`normalized_row` must reproduce every canonical JSONL byte. All required raw
bar open/close fields and SIP price, size, exchange, condition, identity, tape
and nanosecond timestamp fields survive. Each selection is committed together
with its original zero-based source record ordinal, preserving same-timestamp
provider order. No sorting, deduplication, execution-eligibility filtering or
odd-lot reclassification occurs in this stage.

The 09:59 raw bars remain available as hashed source evidence. The entry
scanner's existing cutoff is unchanged. Any later management projection must
apply the frozen completed-bar timing rule to its own signal window; merely
selecting a bar here does not make its close causally usable at its start.

## Exact uncovered tails

The original request envelopes fully cover 51 of the 56 merged windows. The
other five have reusable prefixes and uncovered tails beginning at exactly
10:00 New York time. There are 102 fully covered resources and 10 partial
resources, because each window requires both raw SIP bars and SIP trades.

| Date | Symbol | Missing start, New York | Missing exclusive end, New York | Resources |
|---|---|---|---|---:|
| 2025-06-09 | TPST | 10:00:00 | 10:00:00.946767019 | 2 |
| 2025-06-12 | XTIA | 10:00:00 | 10:11:00.038644945 | 2 |
| 2025-06-13 | JVA | 10:00:00 | 10:11:29.842083339 | 2 |
| 2025-07-02 | LIXT | 10:00:00 | 10:03:08.881827631 | 2 |
| 2025-07-07 | MBIO | 10:00:00 | 10:01:26.113575281 | 2 |

These tails are set entirely by the original decisions and capture endpoints.
They are not an extension of the frozen management windows. JVA remains in the
management population despite its unavailable entry quote. No source, symbol,
date, scenario or opportunity is substituted.

## Unarmed missing-input registration

`research/strategy/sealed-historical-management-missing-inputs-v0.1.json`
records the exact ten missing resource requests. It requires the existing
Alpaca SIP subscription, raw one-minute bars, explicit historical `asof`,
ascending pagination, a 10,000-row page limit and the exclusive endpoint
encoded as one nanosecond earlier on the wire. URL rendering is implemented
and tested; no provider transport is present in this stage.

The registered ceilings are 512 HTTP attempts across the separate child ledger,
100,000,000 normalized compressed bytes and 16,000,000 bytes per response, with
at least 0.35 seconds between requests. These are maximum pagination bounds,
not a forecast of requests. Automatic retries, redirects, workflow reruns,
provider purchases and modification of retained captures are prohibited.
An exhausted empty segment must retain a zero-record receipt without becoming
an inferred account or exit outcome.

A separately tested capture implementation, a verified reuse result, an exact
execution child and durable consumption before provider access remain required.
The user's continuing operational authorization covers development of this
dependency; this input registration itself cannot make market-data calls.

## Reproducibility and next dependency

The CLI installs the existing network/subprocess audit guard before loading the
verifier. A build is write-once. Verification reconstructs every output byte
from the two exact source ZIPs and rejects changed or additional output files,
including edits whose content hashes have been recomputed.

```bash
PYTHONPATH=src:scripts python scripts/verify_sealed_historical_management_reuse_v01.py --validate-registration
PYTHONPATH=src:scripts python scripts/verify_sealed_historical_management_reuse_v01.py --build --sip-zip /path/to/retained-sip.zip --bars-zip /path/to/retained-bars.zip
PYTHONPATH=src:scripts python scripts/verify_sealed_historical_management_reuse_v01.py --verify --sip-zip /path/to/retained-sip.zip --bars-zip /path/to/retained-bars.zip
```

The frozen output root is
`research/runtime/sealed-historical-management-source-reuse-v0.1/`.
It contains source verification, reuse coverage and selection commitments,
the exact missing requests, readiness and a freeze manifest. The dedicated
GitHub workflow downloads only the two retained GitHub artifacts and verifies
them offline under the hash-locked CPython environment. It has no market-data
credentials or acquisition step.

Next: implement and validate a separately consumed capture for the exact ten
missing resources, then verify and compose all management sources before any
projection. Executable exits, causal next-session valuation and account replay
remain later dependencies. Descriptive SIP evidence cannot close account
positions or make portfolio financial metrics eligible.

## Independently verified result — 2026-09-07

The full source reconstruction exactly reproduced all five output files,
totaling 329,301 bytes. A separate stdlib checker with no runtime imports checked
all 1,036 source files, all 510 uncompressed tape hashes and counts, independently
partitioned every management request and verified every selected record against
the retained raw fields and original record ordinal.

| Verified population | Count |
|---|---:|
| Original logical source rows | 20,078,306 |
| Reused SIP prints normalized again | 3,625,859 |
| Reused raw minute bars normalized again | 944 |
| Complete management request envelopes | 51 |
| Partial management request envelopes | 5 |
| Exact missing bar/trade resources | 10 |
| Unavailable entry opportunities preserved | 23 |

The freeze-manifest content commitment is
`b8364219670b5f618334e18a8c9f8f9759e96d8ee64f608fc1ddd1ed076b57de`.
The [permanent independent audit](../../research/data-audits/sealed-historical-management-source-reuse-v0.1-independent-verification.json)
retains both verification reports, the separate checker source, file commitments,
the local environment and test evidence, and verified protected references.

All 1,655 repository tests passed locally with zero skips. The 75 focused tests
passed normally and with optimization enabled under CPython 3.12.13 and the
existing 29 hash-locked packages. Undefined-global checks also passed. GitHub
Actions records the publishing commit's reconstruction under CPython 3.12.14
separately.

The original 30,522-request source ledger and both retained capture ledgers
remain unchanged. This verification made zero new market-data calls and
produced no account, fill, management or backtest outcomes.
