# Discretion held-out labels and comparison v0.1

Status: **retrospective evidence and component comparison frozen; no runtime or policy change**.

## Question answered

The ten-session runtime was frozen before the recap material was opened. This pass asks a deliberately narrower question: when Ross explicitly traded or explicitly rejected a frozen candidate, what did the already-frozen scanner, Micro-v0.1 replay and descriptive context shadows show?

It does not ask which threshold would maximize agreement. It does not create an overall imitation score. It does not treat an unmentioned stock as a rejection.

## Causal order preserved

1. The ten dates and all 119 market candidates were registered without Ross behavior.
2. The scanner, Micro-v0.1 and discretionary-shadow artifacts were generated label-blind and frozen by content hash.
3. Only then were the supplied captions reviewed and encoded in a separate retrospective artifact.
4. The comparison reads both frozen sides but has no runtime effect.

The frozen inputs are:

- scanner runtime content SHA-256 `2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48`;
- Micro runtime content SHA-256 `feb2283acf1f180fd82b0e3c25acde1ebb9ebc036c47533e1d61fc9e8883e190`;
- discretionary-shadow content SHA-256 `e179e8c52e0baf64e27df7ab213012d326e98523ea8279740448386b76c480da`; and
- retrospective label content SHA-256 `4dd31df3fcace0bcc0b52045c748a1a91e00130867394e21c605af5f42007204`.

The comparison content SHA-256 is `809d4b4a7231b708f9c933c9bf45b58c736f4d3101c8328483c62c1c48bcfb3d`.

## Source batch and transcription safeguards

The supplied source was the 300-record file `dataset_daytradewarrior-part-1-1786762403787_2026-08-15_02-53-57-508.json`, SHA-256 `c59a8dd67bf4cb2b3bb4539996bbe1b648b1503a73916371b2f98661a4d33db0`. Fifteen records cover the ten registered dates. The raw batch is not committed and is prohibited from runtime; the repository retains source IDs, caption hashes, short paraphrases and explicit correction provenance.

Caption text is not assumed to be exact. Nine ticker corrections are recorded rather than silently applied:

- `GMMM` -> `GMM`;
- `PLMS` -> `PLSM`;
- `JTI` -> `JTAI`;
- `VIVS` externally confirmed as VivoSim Labs;
- `NVE` -> `NVVE`;
- `Ruby` -> `RUBI`;
- `BYA` -> `BIYA`;
- `LAT` -> `LABT`; and
- `IMN` / `IMM` -> `INM`.

JTAI, VIVS and RUBI were additionally corroborated against same-day public company/news records. Every correction and corroboration URL is retained in the machine-readable label artifact.

## Conservative label policy

Main and small accounts remain separate. The only allowed action states are participated, explicitly skipped/rejected, discussed but unclear, unmentioned/unobservable and source unavailable.

An order attempt without a fill is not participation. A recap saying that Ross took no trade does not convert every unmentioned candidate into a skip. This matters because the source videos are selective recaps rather than complete synchronized decision logs.

Across 119 candidates per account, the sparse labels expand to:

| Account | Participated | Explicit skip | Unclear | Unmentioned | Source unavailable |
|---|---:|---:|---:|---:|---:|
| Main | 9 | 7 | 2 | 101 | 0 |
| Small | 9 | 2 | 2 | 106 | 0 |

The explicit same-day evidence is:

| Date | Frozen-candidate evidence | Observed off-candidate evidence |
|---|---|---|
| 2026-07-10 | GMM main trade; GMM small attempted/no fill; JZXN main skip | none |
| 2026-07-13 | PLSM and VEEE trades in both accounts; QTTB and MIMI main skips | none |
| 2026-07-14 | NXTC and UBXG trades in both accounts | JTAI main trade |
| 2026-07-15 | ERNA small trade/main skip; NVVE main skip | VIVS trade in both accounts; VEEE main skip |
| 2026-07-16 | RUBI small trade; ATAI small skip | none |
| 2026-07-17 | SDOT main skip; BIYA main action unclear | none |
| 2026-07-20 | BIYA trade in both accounts | none |
| 2026-07-21 | no frozen candidate was explicitly labeled | CPHI skip in both accounts |
| 2026-07-22 | LABT trade in both accounts; INM unclear in both; ZCMD main skip | none |
| 2026-07-23 | EHGO trade in both accounts; ZCMD main trade/small skip | none |

## Scanner acquisition result

The scanner acquired 9 of 11 observed main-account participation decisions and 9 of 10 small-account participation decisions. Collapsing account duplicates, it acquired 11 of 13 observed traded symbol-dates, or 84.6% descriptively.

The two missed traded symbol-dates were JTAI on July 14 and VIVS on July 15. These are acquisition misses, not Micro failures: no Micro or shadow feature exists for a symbol that was never admitted as a market candidate. The small panel cannot determine whether a scanner rule should change, but it proves that downstream chart tuning alone cannot reproduce every documented trade.

## Micro-v0.1 component result

| Account | Human trade + modeled fill | Human trade + no modeled fill | Human skip + modeled fill | Human skip + no modeled fill |
|---|---:|---:|---:|---:|
| Main | 6 | 3 | 2 | 5 |
| Small | 6 | 3 | 0 | 2 |

The unchanged Micro rule produced a fill on six of nine acquired documented trades in each account. It missed acquired documented trades in UBXG, RUBI, LABT and July 23 ZCMD, with account overlap reducing these to four distinct symbol-dates. It also produced fills on two main-account skips: ERNA on July 15 and ZCMD on July 22.

Those disagreements are useful. ERNA was traded in the small account but skipped in the main account even though the same technical replay applies to both. That is direct evidence that account state, buying power, divided attention, entry timing and discretionary sizing cannot be represented by one account-agnostic Micro signal.

First-fill prices, pullback numbers and plan counts are retained for case-level diagnosis. They remain descriptive retrospective evidence and are not optimization targets.

## Context-shadow result

Attention/leadership is more aligned with the explicit decisions than a simple news-present flag:

- main-account trades had median activation rank 3, median best rank 1 and became the market leader in 6 of 9 cases;
- main-account skips had median activation rank 4, median best rank 3 and became the market leader in 1 of 7 cases;
- small-account trades had median activation rank 3, median best rank 1 and became the leader in 5 of 9 cases; and
- the two small-account skips had median activation and best rank 5 and never became the leader.

The counts are small and cannot define a rank threshold, but they support Ross's repeated emphasis on the stock becoming obvious and taking over market attention.

Simple provider-news presence is not enough. Seven of nine main trades and four of seven main skips had provider news at activation; five of nine small trades and both small skips did. Some documented trades were explicitly driven by no-news/theme behavior, while other decisions depended on the substance or credibility of a headline. The next context work therefore needs structured catalyst interpretation, theme/regime and daily-chart context—not merely a binary news flag.

## Decision

- Keep Micro-v0.1 frozen.
- Do not tune a volume, pullback, rank or news threshold on this panel.
- Retain attention/leadership and catalyst chronology as descriptive shadow evidence.
- Treat scanner acquisition, candidate/context judgment and Micro participation as separate gates.
- Next preregister deterministic translations where the evidence is measurable; use AI only as a structured, causal, abstaining shadow reviewer for judgments such as catalyst substance, theme fit and ambiguous chart/context quality.

This pilot demonstrates a working evidence architecture and exposes missing layers. It does not establish exact Ross imitation, profitability, a complete trade-selection policy or readiness for live money.

## Reproduction

After extracting the exact frozen Micro and shadow artifacts, the comparison is regenerated with:

```bash
PYTHONPATH=src:. python -m scripts.summarize_discretion_heldout_behavior \
  --labels research/data-audits/discretion-heldout-labels-v0.1-2026-08-18.json \
  --runtime-audit research/data-audits/discretion-heldout-runtime-v0.1-2026-08-17.json \
  --micro-root /path/to/discretion-heldout-micro-runtime-v0.1 \
  --shadow-root /path/to/discretion-heldout-shadow-runtime-v0.1 \
  --output /tmp/discretion-heldout-comparison.json
```

The script validates the Micro root and every candidate replay, validates the shadow root/date hash chain and causal knowledge flags, checks all 119 activations against the scanner audit, and only then joins the retrospective labels.
