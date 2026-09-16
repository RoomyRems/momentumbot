# Scanner minute ordering repair and continuation

The original code `d8c9e768bf13939b321bfc2ef81be7458ae239c9` passed CI
`34980869407`: 2,980 tests in 494.715 seconds, 73 optional skips and compilation.
Capture `34980869608` then stopped after 87 requests. Its 85 completed roots
contained 643,276 minute bars. The failed original report and all 264 archive
members were retained; original artifact `10401713219` is 13,788,429 bytes,
SHA-256 `6f18fbeff5f329b26c1eff6cb7dc188ceb5c7340abec200047456f53350fb2ba`.
The original consumption tag is permanent. Do not rerun it.

At root 85 (March 9), page one ended at symbol `RUN`; page two contained `R`,
then `RUN`, `RUSHA`, `RUSHB`, `RVI` and `RVLV`. There were no repeated or
regressing timestamps within a symbol. The 20 `R` bars first arrived on page
two. A global lexicographic cross-symbol assumption caused the rejection.
This is an observed provider-page ordering issue; no cause beyond those bytes
is asserted.

The v0.2 parser retains the original bar lists and applies strict increasing
timestamps independently for every requested symbol across all pages. The
original parser still rejects the saved response. All schema, OHLC, date/grid,
population, duplicate, cursor, exhaustion, HTTP, credential and size checks
remain. The change does not infer an identity merge or alter scanner policy.

Replaying the original 87 responses under this narrow repair completes 86
roots and preserves 653,465 bars. The new registration contains only the
remaining 604 roots. The combined attempt ceiling stays 13,800; the original
payload and metadata byte use are subtracted from the continuation's limits.
The existing 150-minute per-run time and 350 ms minimum pacing remain.
Full same-code CI and a separate durable consumption precede credentials.

The original ZIP is committed as two byte-exact parts named
`research/data-audits/early-pullback-scanner-minutes-v0.2/original-prefix.zip.part000`
and `.part001` to fit the connector's upload limit. Their concatenation must
match the original ZIP's complete byte count and SHA-256 before it is opened.
The verifier checks its complete byte inventory, original request/receipt
sequence, original failed report and preserved completed results. It then
replays the suffix ZIP and checks that the combined root union equals the
original 690 roots exactly. Neither the successful pages nor the rejected
response is downloaded again. Prefix and suffix retain their original,
distinct source identities.

The generic scanner CLI now takes its source module explicitly. This permits
future source stages to reuse the driver without editing a frozen launcher.
Focused tests cover the observed failure, strict per-symbol order, unchanged
schema/transport checks, remaining scope and synthetic original-ZIP replay.
The September 16 handoff revalidated all 23 scanner-minute and continuation
tests normally and with assertions disabled; compilation also passed. The
retained logs describe local verification only. Full GitHub CI and the hosted
capture/verification outcome remain separate checks on the publication commit.

After completion, compose the two accepted source segments for scanner input.
Keep the saved-daily share-basis check and raw/RVOL/float/news work described in
`scanner_minutes.md`. The 4,018-case acquisition-only superset is already saved.
Historical runtime, discretionary trading authority and financial evaluation
remain closed; discretionary context can be exercised as a separate shadow.
