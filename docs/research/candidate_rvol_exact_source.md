# Exact-minute RVOL source integration

This additive integration consumes the original independently verified capture
from run `35408612330`, at code `53989a5f1637e759a3922980b40f24cbfbaab5fb`.
It does not renew its consumed authorization or make market-provider requests.

The original verification ZIP is preserved under
`research/data-audits/early-pullback-candidate-rvol-exact-source-v0.1/`.
Its SHA-256 is `28abe4f51d6f30bef687fb348d549b8283e78934bfc949f9ec14be1bb5da661a`;
the original 63,526,941-byte capture ZIP is bound to
`1c8f6358bdf684e796ed1006ed4d6da49af491523d9b38227a4a2565aad4fc17`.
The verification proof seal is
`0afe76dc958b0cf2f03ba48efcbf3a3f6b15a6a735f531558de87acc223e48f7`.

## Contract

- Keep the frozen selection of 2,103 candidate/date cases, each with fifty prior
  observed sessions. Preserve the 1,675 coarse exclusions and 240 empty or
  short-history exclusions. No outcome-based selection is introduced.
- Revalidate exact original request/page bytes, declared session dates, original
  summaries, inventory hashes, exhausted empty frames and candidate populations.
- Compare each exact historical morning with its accepted coarse counterpart
  using exact rational sums over all 24 fifteen-minute buckets. Coarse volumes
  validate consistency; they never enter the RVOL calculation.
- Reuse accepted target-minute volumes except for the eight registered refreshes.
  Those refreshes must match the coarse target buckets and raw-minute timestamps.
  Retain the original disagreement; never infer or apply a split multiplier.
- Withhold the entire affected curve if a target/history comparison or timestamp
  alignment disagrees. A zero-volume exhausted session is present history; a
  missing session is an error. No invalid input is replaced with zero.
- Reuse `same_time_rvol` and `align_exact_rvol_to_raw_bar_indexes_v10`.
  Produce values for observed raw bars with starts from 04:00 through 09:59 ET,
  available only after the corresponding minute closes. The 10:00 bar is not
  covered by this history. Preserve undefined values as JSON null and positive
  infinity as `positive_infinity`; do not convert them to zero or finite values.

These outputs supply exact-RVOL source values, not a completed historical
scanner. Daily/minute price/share-basis checks, historical float/news, the full
captured-source scanner adapter and discretionary shadow integration remain
separate. Raw price, raw execution volume, risk policy and frozen experiments
are unchanged. Original capture and comparison evidence are immutable.

## Reproduction

Fetch only the four existing byte-pinned GitHub artifacts using
`scripts/fetch_candidate_rvol_exact_sources.py --output <fresh-directory>`.
This needs GitHub CLI artifact read access, not market-provider credentials.
Artifacts remain subject to their original GitHub retention windows; expiration
does not authorize a new capture.

Run `scripts/audit_candidate_rvol_exact_source.py` with `PYTHONPATH=src:scripts`,
passing `--exact-capture`, `--coarse-capture`, `--raw-capture`, `--split-capture`
and a fresh `--output` directory. After input setup, a Python audit hook denies
network and subprocess access. Per-date outputs and the final report are sealed;
their hashes bind the exact series, source evidence and unresolved comparisons.
The current observed result is recorded in the
[work item](../agent-workflow/runs/exact-rvol-source-2026-10-16/CONTEXT.md).
