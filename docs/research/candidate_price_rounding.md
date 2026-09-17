# Candidate price precision and volume projection

Parent `de5ec099fc189114900fc545167ca79da271eb29` passed CI `35164380438`:
3,028 tests in 510.976 seconds, 73 optional skips. Coarse RVOL capture
`35164380485` passed its exact-code gate and began provider collection.
Capture completion and source acceptance are separate from that CI result.

## Offline price diagnostic

The original strict comparison remains unchanged: 175 of 3,892 nonempty
candidate/date pairs had price residuals, with 126 additional empty pairs.
The new diagnostic reads the same pinned original raw and split archives and
the saved daily raw/split highs. Full-day highs are diagnostic evidence only;
they never enter causal runtime features or acquisition priority.

`candidate_price_rounding.py` intersects exact rational factor intervals for
every paired minute close and the saved daily high. It uses decimal values
as reported and closed half-quantum boundaries, leaving tie-breaking unknown.
It neither fits an epsilon nor applies an inferred factor to a source price.

The initial nearest-cent hypothesis finds 3,717 exact constant-factor cases,
155 compatible rounding cases, 20 cases off the cent grid and 126 empty pairs.
That full original result is retained as `rounding-diagnostic.json.gz`, seal
`e330762c1964383327d411b46c771d0d56cb146730c81717ed7dcd8df3886931`.

Inspection of the 20 off-grid cases found three-decimal adjusted prices below
$10, for example TRNR 1.425 -> 9.975 and 1.4002 -> 9.801. A separate,
explicitly post-hoc hypothesis uses nearest 0.001 below $10 and nearest 0.01
otherwise, selecting precision from the reported adjusted value. Across all
4,018 cases it finds 3,717 exact, 175 compatible and 126 empty pairs, with no
incompatible cases. Its seal is
`a74bcc55f7e64ad54990a800e6c85f9ba0612d6c62a67c823a3c855aebb9acf8`.
Both losslessly compressed outputs and original audit logs are retained under
`research/data-audits/early-pullback-candidate-price-rounding-v0.1/`.

This explains the observed residuals empirically. It does not document the
vendor algorithm, prove half-quantum tie behavior, establish the complete
ranking population's adjustment basis, or authorize runtime normalization.
It is not a strategy change or a calibrated trading threshold. The original
strict diagnostic and its failed cent-only explanation remain available.

## Volume helpers for the incoming capture

`candidate_volume_projection.py` adds a pure source-page projector that reuses
the frozen coarse parser and checks the accepted root summary before emitting
volume frames, including exhausted empty symbols. A separate selector reads
original split-minute volume fields from already byte-pinned full-membership
archives, preserving source counts and the full ranking population.

The overlap diagnostic compares all 24 completed 15-minute buckets between
04:00 and 10:00 ET using exact rational sums. It rejects wrong dates, duplicate
or off-grid timestamps and invalid volumes; 10:00-start minute volume is
excluded. Missing bars count as zero only when the caller has established
exhausted provider pages. Every differing bucket is retained, with no fitted
volume tolerance. Matching target buckets would not establish prior-session
volume consistency or authorize pruning by themselves.

These are tested integration helpers, not a claim that the pending hosted
capture is already accepted. Fourteen focused tests pass normally and with
assertions disabled. Exact one-minute RVOL, complete adjustment-basis checks,
float/news and the additive scanner discretionary-shadow bridge remain.
Trading policy, account replay and order authority are unchanged.
