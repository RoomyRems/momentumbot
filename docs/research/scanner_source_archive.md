# Accepted scanner minutes and combined source reader

Parent `cefb30e3d006e41634f510236c08dafe4a46f170` passed full CI
`35105447076`: 2,987 tests in 265.546 seconds, with 73 optional skips and
successful compilation. Continuation `35105447180` passed all three jobs and
every step. Independent hosted verification accepted all 690 original roots,
165,694 member/date records and 5,230,052 minute bars across all 30 dates.
It reused 87 original responses and made 616 new requests: 703 total.

The original failure, consumption tags and prefix remain unchanged. The saved
verification ZIP, consumption ZIP and terminal GitHub metadata are retained in
`research/data-audits/early-pullback-scanner-source-v0.1/`. The continuation
capture is original artifact `10450218482`, 92,363,559 bytes, SHA-256
`a8b3516932f4fbe8c076e7a644687848498d71eee71e4594fd3f49a724300ef4`.
Its recorded GitHub retention expires December 15, 2026. Keep this original
artifact or byte-exact parts for subsequent source work.

## Source integration

`ScannerMinuteArchive` combines the immutable prefix with the accepted
continuation. It pins the original hosted verification ZIP, requires the
original continuation byte count and digest, reproduces the repaired prefix,
and builds an exact index of all registered roots. It does not trust a new
caller-generated proof. No provider credentials or calls are involved.

The reader accepts the original capture ZIP or ordered parts whose concatenation
matches that same ZIP. It retains verified bytes while open, preventing later
filesystem changes from replacing source data. This supports environments that
cannot retain a large single file across sessions; it does not recompress or
substitute an archive. A truncated local copy was correctly rejected during
development, and that failure log is preserved.

Each dated read requires the complete frozen membership and original root
union. It checks consumed source-member bytes, reuses strict per-symbol
pagination validation and compares the result with the accepted root summaries.
It returns saved previous closes and split-adjusted close frames for every
member, including explicit empty frames. Failed/missing pages cannot become
empty-symbol exclusions. Source provenance retains segment, member, body and
request identities. Bar timestamps remain starts; the scanner must still wait
until start plus one minute. The inclusive 10:00 source bar is not available
to a 10:00 decision.

The new offline command projects all 30 dates and records counts and lineage:

```bash
PYTHONPATH=src:scripts python -O scripts/verify_scanner_source_archive.py \
  --capture-zip /absolute/path/to/original.zip \
  --output /absolute/path/to/new-source-verification.json
```

For parts, pass all paths after `--capture-zip` in original byte order. The
output must be new. The command denies network and subprocess I/O. It is a
source projection, not another account replay or a financial evaluation.

All 30 dates projected successfully with assertions disabled: 165,694 dated
member frames and 5,230,052 bars, with every original source page retained.
The source-verification content seal is
`137958a2b3ece3003f8e08bd1923f7a41ae191e33bc63692a1a4ac91ed2a844d`.
All ten focused tests pass normally and optimized; compilation passes. The
first CLI invocation exposed a missing repository import path, which was
corrected and covered by a CLI regression test. Both that failure and the
truncated-copy rejection remain recorded. Full CI for this new reader is a
separate publication check; the parent CI result above is not reused as its CI.

## Remaining integration

This is the full-membership ranking source, not the complete scanner. Daily
and minute split-adjustment bases still need agreement or explicit normalization.
Candidate raw minute bars, exact same-time RVOL history, point-in-time float
and publication-timed news remain necessary. Reuse the saved 4,018-case
acquisition superset to bound candidate requests; its full-day filter values
must never enter runtime features or AI prompts.

The existing semantic context contract names scanner v0.1. Connect current
scanner v0.3 through an additive adapter and contract, preserving older shadow
artifacts. The existing compiled rubric is not model-driven inference. New
context can run in shadow before final paired account evaluation, with missing
evidence producing explicit abstention. Strategy, risk, trading authority,
fixed dates and the two-arm experiment remain unchanged.
