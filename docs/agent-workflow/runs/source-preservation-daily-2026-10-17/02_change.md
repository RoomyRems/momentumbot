# Change — original-source preservation and prior daily inputs

Source implementation commit: `c6ccce6155d02d3f0868784a9be646d2437698e7`.

Added `candidate_daily_source.py`, an offline pinned-archive reader that reuses
the frozen daily-history projector and member/lifetime protocol. It requires
the original archive pin and proof, validates original pages, and retains empty
or insufficient histories rather than padding them. Previous-close comparisons
use the witness's exact prior session and rationalized decimal values, with no
tolerance or fitted correction. The audit runner blocks external I/O.

The all-date child evidence contains 318,519 daily bars, 4,018 cases and 30 dates.
All 4,018 saved previous closes match exactly and refer to the latest history
session. Original fifty-session average volume is available in 3,904 cases;
114 remain unavailable. No full-ranking-population or daily/minute basis claim.

Nine missing original capture/consumption archives were recovered from existing
Actions artifacts, checked against original sizes/hashes, and successfully saved
outside Actions retention (304,624,592 bytes). The inventory binds all fourteen
references from seven checked proof ZIPs: nine saved files and five exact Git
files. Source proofs and earlier failed prefixes remain unchanged in Git.
The already-saved eight transcript attachments were not reread or duplicated.

No provider run, changed source contract, runtime scanner wiring, label input,
risk/policy change, strategy promotion or live order. External consumers remain
unknown. A private recovery index records saved file identities and restore steps;
the repository inventory intentionally contains no private file identifiers.
