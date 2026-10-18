# Change

Source commit: `80441944c3ac3ab050d13a5d323c76e76a7ab212`.
`CandidateFeatureInputs` joins the pinned daily report and exact-RVOL report by
date and symbol. Each dated file must match its original hash, byte count and
seal; its ready case population must exactly match the supplied curves.

The reader supplies previous close, original fifty-session average volume and
decoded RVOL curves through one interface. It retains all daily cases, original
undefined/infinite RVOL, and explicit absent/disagreeing exact histories.
`completed_curve` returns only observations whose minute has closed.

No full scanner construction, normalization, model inference or provider I/O.
Float/news, full ranking and source-wide basis remain incomplete. The older
float/news audit inspected covers different dates and is not reused as evidence
for this panel. Previously established price-rounding diagnostics are unchanged.
