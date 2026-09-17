# Accepted RVOL sources and exact-minute acquisition preparation

The frozen code parent is d6360a51dd0490a51044959e3c9bbfd619590cda.
Its CI 35165667435 passed 3,042 tests in 547.114 seconds with 73 optional
skips. Coarse capture 35164380485 and its independent verifier succeeded:
1,530 roots, 1,543 requests, 1,286,624 bars and 192,678 symbol/session
observations, including 8,932 exhausted empty observations.

The accepted proof seal is
5c6e6f3e9f3c2f16ba513f186d4c6041bfa0939d754195c26a811b8e58f3b7e5.
Original capture artifact 10475116749 is 31,719,387 bytes, SHA-256
11c2bbfe5f13b977e220ce8b23971836bef2b29047c21da129a541c2f510f5b8.
Original verification artifact 10474627567 is 796,826 bytes, SHA-256
8ac9bae226bdfc723fad418a8e9ba7bb9483be3ea07d8bd1a2d5e5921b0200f4.
These existing artifacts expire on December 15, 2026.

## Integration

CandidateCoarseArchive binds the exact original proof and capture bytes,
validates the frozen contract, checks source members and replays each root
before emitting all fifty prior sessions plus each target morning. Explicit
empty frames are retained. The reader does not download from a market provider.

The offline audit compares all 24 completed target-morning volume buckets
with accepted split-minute data, using exact rational sums. A differing target
bucket retains the entire case for exact acquisition. The conservative
completed-bucket RVOL filter uses only accepted historical split aggregates,
the target cumulative split volume and the unchanged necessary raw price/time
predicate. No gain, rank, float, news, transcript or outcome-based filter is added.

The bound is the existing completed-15-minute acquisition rule, evaluated
with exact rational arithmetic: current cumulative volume times 50 must reach
the frozen 5x threshold times the sum of completed historical bucket volumes.
The incomplete historical bucket is excluded. Zero historical volume with
positive current volume retains the case. Zero current volume does not qualify.
This assumes the provider's split aggregate volumes represent the same share
units across the requested histories; target discrepancies are explicitly
retained rather than normalized. Coarse RVOL values never enter the scanner.

The generated request plan contains fifty unique prior observation dates for
every retained case, requests split SIP 1Min bars through 09:59 ET, and preserves
each target date's entity mapping. Existing target-minute bars are reused.
The report prepares requests only; it does not authorize or perform capture.
A following bounded, exact-code-CI-gated capture must bind the final report seal.

## Verification and interruption

Four initial reader tests passed locally normally and optimized before the
workspace disconnected. The all-date local diagnostic was interrupted; partial
logs showed both exact matches and discrepancies and are not accepted as a
completed result. Additional acquisition-filter changes were not locally
verified after the disconnect.

The additive GitHub workflow runs all seven focused tests normally and
optimized, retrieves four byte-pinned existing GitHub artifacts, and executes
the optimized offline audit. It preserves success or failure, exact source
metadata and the complete prepared request report. It needs only read access
to GitHub Actions, and has no market-provider credentials. The ordinary full
CI runs separately for the same commit. Hosted results remain pending at
publication; no source-filter success or next capture is claimed in advance.

The prior losing baseline, account/risk policy, causal-input boundaries and
discretionary shadow-only authority are unchanged. Exact-minute RVOL acquisition,
remaining adjustment-basis checks, historical float/news and the scanner-to-
discretionary bridge remain the next integration work.
