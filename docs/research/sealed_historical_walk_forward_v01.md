# Sealed historical walk-forward v0.1

## Purpose

The August 24–September 4 prospective panel is closed after five operationally
incomplete dates and before the remaining five dates began. It produced no
opportunity freeze, no evaluable account cell, no Databento acquisition, and no
order. Failed dates remain failures; they are not zero-opportunity observations
and will not be retried or backfilled.

The replacement experiment is a 30-session historical walk-forward using the
same frozen scanner profiles, Micro-v0.1, account rules, execution scenarios,
management rule, and component evaluation. Only the data transport and session
sampling change.

## Frozen parents

- Research parent: `a2d2ffe5959fce7b4f4733528df4f873ea1913be`
- Micro-v0.1: `49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa`
- General profile: `7d15fb979701324bf862b1dc37e5f9b514dcf1ab8cf1e062ae4a60027233d4ff`
- Small profile: `fb86fc5326903cab16c283a03d8e371f66487f41589fb1b69b79f8912a0a6489`
- Daily source, account runtime, management capture, and evaluation contracts
  remain exact hash-bound parents.

No threshold, setup family, symbol exception, account rule, execution scenario,
or management rule may change inside this experiment.

## Label-blind selection

The transcript inputs are committed as eight opaque byte streams. The manifest
records only logical part, serialization, byte count, structural record count,
and SHA-256. It does not decode or persist any record value. Titles, captions,
publication dates, tickers, Ross actions, and outcomes are not selection inputs.

The candidate interval is January 2, 2025 through June 30, 2026. Weekends,
exchange holidays, early-close sessions, and every valid ISO date referenced by
the frozen prior research inventory are removed. The remaining sessions are
partitioned chronologically into non-overlapping 30-session blocks. A SHA-256
over the contract ID, calendar ID, Micro fingerprint, corpus-manifest hash, and
exclusion-manifest hash selects exactly one block. The final partial block is
discarded before selection.

The frozen selection is:

1. 2025-05-30
2. 2025-06-02
3. 2025-06-03
4. 2025-06-04
5. 2025-06-05
6. 2025-06-06
7. 2025-06-09
8. 2025-06-10
9. 2025-06-11
10. 2025-06-12
11. 2025-06-13
12. 2025-06-16
13. 2025-06-17
14. 2025-06-18
15. 2025-06-20
16. 2025-06-23
17. 2025-06-24
18. 2025-06-25
19. 2025-06-26
20. 2025-06-27
21. 2025-07-01
22. 2025-07-02
23. 2025-07-07
24. 2025-07-08
25. 2025-07-10
26. 2025-07-11
27. 2025-07-14
28. 2025-07-15
29. 2025-07-16
30. 2025-07-17

Dates may not be replaced. A provider or coverage failure makes that registered
date unavailable and remains visible in the result.

## Execution sequence

1. Validate all registrations provider-free.
2. Confirm each selected date is a full provider session and obtain sanitized,
   bounded availability/cost evidence.
3. Freeze point-in-time membership, identity, corporate actions, float, news,
   prior daily bars, and complete causal intraday cross-sections.
4. Run the label-blind scanner and Micro source for every date.
5. Acquire candidate-bound execution/status data only after an exact quote and
   separate bounded authorization.
6. Replay the two accounts chronologically across all dates for each of the
   three horizons and two execution scenarios. This creates 360 dated cell
   records; accounts do not reset between dates.
7. Freeze the complete runtime hash chain.
8. Only then verify the original transcript hashes, open retrospective evidence,
   create account-scoped labels, and evaluate all cells separately.

No transcript title, caption, Ross action, fill, skip, recap judgment, later
price, final volume, or P&L may enter steps 1–7.

## Decision limits

The report must include acquisition, observable trade/skip agreement, entry and
exit alignment, activity, unavailable rates, account results when complete, and
best-trade-removed sensitivity. It may not rank or select a cell, fit a weighted
imitation score, retune the policy, claim profitability, or authorize paper/live
orders. Any later promotion is a separate decision after all registered results
are preserved.
