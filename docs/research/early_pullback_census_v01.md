# Early-pullback census adapter v0.1 — unarmed

## Frozen parent and hypothesis

Parent commit `a1bdf9711183937cb55d539a3514606c77db07d6`, tree
`a51a8fad2133270187229c18dca7957bb0bc84a5`, planner registration
`a8111ed4eb7a64c76dbeceae51f580680c0e0ecce627402e89db10b94a452ff1`.
The one hypothesis is mechanical: bounded one-pass capture and independent
byte replay can distinguish an exhausted census protocol from missing,
invalid or interrupted inputs. This is not a strategy or profitability test.

The 30 dates, original strategy, scanner, account mechanics and losing baseline
are unchanged. The four-call availability authorization remains permanently
consumed. No transcript records were read. Recap actions/fills, later outcomes,
evaluation narratives and performance-selected substitutions remain prohibited
inputs to capture, replay and runtime prompts.

## Implemented boundary

`early_pullback_census_v01.py` provides a single-pass session with mandatory
injected transport, strict response projection, shared deterministic page
transitions, exclusive retained files, sanitized attempt receipts, an inventory,
and an independently pinned ZIP verifier. `early_pullback_census_http_v01.py`
provides a fixed-host HTTPS callable, but there is no hosted capture launcher.
The only shipped CLI validates/freezes the registration under an external-I/O
deny hook. It has no capture mode, credential argument or environment discovery.

The callable alone is not authorization. A future separately registered launcher
must validate the complete frozen registration, exact tested parent, single-use
authority and subscription entitlement before supplying credentials/transport.
The session checks registration identity, seal and limits; it does not prove
the supplied contract's provenance or implement hosted durable consumption.

| Limit | Enforced value |
|---|---|
| Initial requests | Current type dictionary plus 30 date-specific census roots |
| Pages / date | 20; needing page 21 fails instead of truncating |
| Rows / page | 1,000 |
| HTTP attempts | At most 601, not an expected response count |
| Request-start spacing | At least 12.5 seconds by monotonic clock |
| Response | At most 16,000,000 bytes; one additional detection byte |
| Combined raw + normalized retention | 1,496,000,000 bytes |
| Metadata reserve | 4,000,000 bytes; total retained ceiling 1,500,000,000 |
| Retries, redirects, fallback | None |
| Current capture / incremental spend authority | Zero calls / USD 0.00 |

Combined raw and normalized retention is deliberately bounded together, rather
than treating the planner's proposed normalized retention cap as an additional
unbounded raw allowance. The HTTPS callable uses 30-second socket timeouts and
a 30-second deadline checked between reads; this is not a hard 30-second total
wall-clock guarantee. It neither follows redirects nor discovers proxies or
credentials. A read failure can retain a digest of completed observed chunks;
that digest is not a complete-response claim.

## Membership, completeness and failure semantics

The exact frozen date/query/cursor/predecessor chain is reconstructed before
every accepted page. JSON rejects duplicate keys, nonfinite numbers, changed
filters, unknown fields, coerced metadata, count mismatch and order regression.
The current type dictionary is captured separately: it does not establish
historical type identity. Missing CIK/FIGI/type/exchange values and unknown
current type codes are counted, not fabricated or silently filtered. Same-ticker
distinct membership identities remain; duplicate membership identities fail.

Every report includes all 30 dates with accepted page/row counts and explicit
`not_started`, `partial` or `exhausted` states. Exhausted empty total membership
fails; empty intermediate pages and empty terminal pages after real membership
can be valid. `exhausted` means the declared response chain ended, not that an
independent exchange master corroborated all historical securities. Corporate
actions, identifiers, float, news and strategy-ready source coverage remain open.

An intent is exclusively written, flushed and file-fsynced before each attempted
exchange. Successful schema-valid raw response bytes and canonical normalized
projections are retained together. Failed, incomplete, oversize, encoded or
credential-echo bodies are hash-only; exception strings are not recorded. A
schema-valid page that fails chain validation remains as evidence but does not
advance accepted state. The first failure stops the pass without retry. Local
interruptions attempt a failure report/inventory; output reuse/resume is blocked.
File fsync is not remote durable consumption, and abrupt process/host loss can
leave pending intents without final metadata. Those captures cannot pass.

## Independent byte verification

The reader requires caller-supplied archive size/SHA-256, inventory-file SHA-256
and a separately validated frozen contract. It rejects unsafe/duplicate ZIP
members, excess retention, population changes, changed member hashes, missing
pages, raw/normalized differences, timing violations, forged receipts/reports
and evidence after exhaustion. It reparses every raw response and reconstructs
the full 30-date sequence rather than trusting a completeness flag. Partial
captures remain evidence but cannot pass the complete-archive verifier.

Hashes supplied by the same untrusted producer do not establish provenance.
Even successful verification leaves provider-origin authentication, historical
identity, historical replay, financial evaluation, paid capture, order authority,
policy promotion and discretionary integration **false**. No raw archive from
this adapter can activate the existing market runtime on its own.

## Verification and evidence

Registration: `1203e49170a69c5c6eb725b77aca997a61872379c69bece4bead42a7ec6a73a7`
with 361 byte-bound files. All 36 focused tests pass normally and optimized.
They include a synthetic 601-attempt terminal-boundary case; no HTTP was issued.
The completed pandas 3 full suite ran 2,661 tests in 383.484 seconds: 2,588
passed, 73 optional SDK skips, zero failures/errors. The dedicated completion
receipt records 384.860 seconds including discovery/wrapper work. Local audit:
`d57026a12a99ca6f6236e777d198e366b9b905a64c308ab93cfba59554381f93`.
The preliminary 35-test check had two absent-registration failures before the
first freeze; its factual record is retained, not reclassified as a pass.

The audit directory `research/data-audits/early-pullback-census-adapter-v0.1/`
holds verification receipts and a clearly synthetic complete archive. Its fake
clock, one invented member per date and missing identity fields are mechanics
fixtures, not market observations or historical-universe evidence. The saved
71,610-byte ZIP independently verified all 127 members; archive SHA-256:
`3045cd894174e6b567d6b7708472b237e62eb2f6313767a28ea49e96d3eb889e`.
Published code `5ff703ca098345b37c37c4bee299e709eb683a4c` passed
[hosted CI 34697041055](https://github.com/RoomyRems/momentumbot/actions/runs/34697041055):
2,661 tests in 349.882 seconds, 73 optional skips, all 36 new tests passed,
compilation and every job step succeeded. The hosted environment installed
pandas 3.0.5 and NumPy 2.5.3. All six legacy validations also passed; their
probe/acquisition jobs were skipped. Hosted verification:
`321a3015f2e7480fb9350ba499498a1d0478eaefebfb1a93cb914c90735cc28b`.
The evidence-only child adds this result without changing tested source.

## Next gate and interpretation

Next is a separate tested exact-parent hosted launcher with durable single-use
consumption and verified provider subscription entitlement. An authorized run
must retain raw bytes and receipts, then bind the archive to independently
verified execution provenance before historical identity/source work. This
implementation does not authorize that run or any paid capture.

The intended hybrid still needs its crucial discretionary/context components.
Losses from incomplete deterministic components do not settle the full hybrid's
edge; completing the hybrid does not guarantee profitability. Offline versioned
transcript design remains separate from all backtest/runtime inputs.

## API references checked 2026-09-12

- [Massive All Tickers](https://massive.com/docs/rest/stocks/tickers/all-tickers):
  PIT `date`, active filter, maximum 1,000-row page and `next_url` response.
- [Massive Ticker Types](https://massive.com/docs/rest/stocks/tickers/ticker-types):
  current asset-class/locale type dictionary, not historical membership proof.
