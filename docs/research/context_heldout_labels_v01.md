# Context held-out retrospective labels v0.1

Status: **frozen conservative retrospective evidence; descriptive component comparison complete; no runtime or policy change**.

## Causal order

The ten trading sessions were registered before source inventory. Deterministic context artifact `9376599434` was then frozen and audited, followed by the label-blind compiled semantic shadow at exact tree `0c899fb80203c13fc4e5b59b758f1690ca892a33`. Only after that tree was published on `phase-3-historical-snapshot` was the supplied archive opened.

The label artifact binds:

- deterministic runtime ZIP SHA-256 `a29186eb092752cfafc031360cacf348bea5e607cb19ce326ddaff2ddfedac1a`;
- deterministic runtime manifest content SHA-256 `3567619bfb6b7b2c177d02cc69f15423bf605663519017a6638b0394e4153702`;
- context snapshot runtime content SHA-256 `6dcc6f25ddb73e63b5f9c714e0c890ab954b15b099e7ba3a71ef948f9760939f`;
- semantic manifest content SHA-256 `9b3be7a17f29e638b0e1da14b4d050762503bab17c74c3f97e62b99489f25cd4`; and
- semantic checkpoint tree `0c899fb80203c13fc4e5b59b758f1690ca892a33`.

The retrospective label content SHA-256 is `3ff85b371de31ea5dc1d2e4afc4e334c6f6f5051bfe5c7340fb51007527b7cd1`.

## Source inventory

The eight supplied files contain 2,292 records. Fourteen records provide evidence for the ten fixed trading sessions. Every panel source is in part 1; all eight file hashes and counts remain recorded so the inventory boundary is complete. Raw captions are not committed or allowed in runtime. The repository retains only metadata, caption hashes, explicit correction provenance and short paraphrases.

Publication date is not treated as the trading date without content evidence:

- `CA8i4Rc2bUY`, published July 24, describes EHGO and ZCMD actions from the excluded July 23 pilot session and is explicitly excluded.
- `coqONALABpo` and `cZcprj_8wEM`, both published August 7, explicitly describe day 31 following the August 5 day-30 session and form the August 6 account recaps.
- `ofCxvrijsss` covers the next, August 7 trading session and is outside the registered endpoint.

No date was replaced. Every registered date has usable retrospective evidence.

## Conservative label policy

Main and small accounts remain separate. A candidate receives `participated` only for a reported completed trade and `explicitly_skipped_or_rejected` only for an explicit no-trade decision. A no-trade session does not convert unmentioned candidates into skips. Discussion without resolved account action remains `not_mentioned_or_unobservable` unless an attempted order or other first-person evidence makes the action specifically unclear.

Across 195 candidate symbol-dates per account, sparse labels expand to:

| Account | Participated | Explicit rejection | Unclear | Unmentioned / unobservable | Source unavailable |
|---|---:|---:|---:|---:|---:|
| Main | 11 | 4 | 0 | 180 | 0 |
| Small | 6 | 8 | 0 | 181 | 0 |

The explicit evidence is:

| Trading date | Frozen-candidate evidence | Off-candidate evidence retained |
|---|---|---|
| 2026-07-24 | MSS traded in both accounts | EXYN traded in both; LVWR main rejection |
| 2026-07-27 | EDBL main trade/small rejection; BIYA rejected in both; DFNS and LGHL small rejection | VTIX traded in both |
| 2026-07-28 | INLF traded in both; DFNS rejected in both | none |
| 2026-07-29 | NCRA main trade/small rejection | DFNS main trade |
| 2026-07-30 | NUWE and PN main trades | DFNS main rejection |
| 2026-07-31 | FCUV traded in both | none |
| 2026-08-03 | FCUV, HYFM and EZRA main trades; HYFM and EZRA small trades; UPC main rejection; FCUV small rejection | none |
| 2026-08-04 | AMIX rejected in both accounts | none |
| 2026-08-05 | YXT small trade; main-account coverage incomplete | none |
| 2026-08-06 | CLRO main trade | DSY traded in both; MB and NAMI main trades |

Off-candidate actions remain acquisition evidence and never receive fabricated frozen context features.

## Transcription safeguards

Caption text is not assumed error-free. Seven corrections are explicit rather than silently applied: `EDGL` to `EDBL`, `NBI YA` to `BIYA`, the `INFL` / `INLX` / `INFS` variants to `INLF`, `AMMX` to `AMIX`, `XYT` to `YXT`, `NMI` to `NAMI`, and `DSW` to `DSY`. The first five resolve to frozen candidates through same-record or companion-record evidence. The latter two resolve only the internally consistent off-candidate identity. The symbol transcribed as `MB` stays unresolved.

## Limits and completed comparison gate

These recaps establish retrospective sequence and account action, not synchronized decision timestamps, complete order history or all opportunity evaluations. They do not expose buying power, divided attention, Level 2, time and sales, complete exits or later opportunity cost to the runtime.

The descriptive, no-fitting component comparison is frozen as `ross-context-heldout-comparison-v0.1`, content SHA-256 `d93d61ed0ebd5657bbed135beb7fe2d7b0f337d1e3f76720c0f1dcff7908ff54`. It reports deterministic coverage, semantic assessed/abstained states and explicit account actions separately. It creates no aggregate context score, tunes no threshold, leaves Micro-v0.1 unchanged, promotes no policy and makes no representative Ross-imitation claim. See `docs/research/context_heldout_comparison_v01.md`.

## Files

- Label artifact: `research/data-audits/context-heldout-labels-v0.1-2026-08-19.json`
- Validator: `src/momentumbot/research/context_heldout_labels.py`
- Tests: `tests/test_context_heldout_labels.py`
- Completed comparison: `docs/research/context_heldout_comparison_v01.md`
