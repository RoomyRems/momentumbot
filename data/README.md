# Data policy

Raw Warrior Trading transcripts are **research input only** and are deliberately not committed to this repository.

Expected local layout when running research tools:

```text
data/raw/daytradewarrior/*.jsonl.txt
```

The source corpus may contain copyrighted transcript text and retrospective daily recaps. Keep it outside version control. Commit only derived metadata, evidence references, rule summaries, tests, and reproducible code.

For historical experiments, publication date is a hard information boundary. A transcript published after the simulated market timestamp is unavailable to that experiment. Records with unknown publication dates are quarantined rather than assumed historical.
