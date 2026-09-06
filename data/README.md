# Data policy

Raw Warrior Trading transcripts are research input only and are deliberately not committed to this repository.

Expected local research layout:

```text
data/raw/daytradewarrior/*.jsonl.txt
```

Commit only derived metadata, stable evidence references, paraphrased rule summaries, tests, and reproducible code.

Historical market snapshots belong under an ignored `snapshots/` directory or in workflow artifacts/object storage. Every snapshot must declare `universe_complete=true`, retain point-in-time float timestamps, and preserve news publication timestamps.
