# 04 — Handoff

## Inputs

### Working inputs

- `runs/<id>/01_scope.md`, `runs/<id>/02_change.md` and `runs/<id>/03_verification.md`,
  using [path notation](../CONTEXT.md).
- The actual published branch/commit and observed hosted-job state, if publishing
  was in scope; otherwise the exact local diff and its not-published status.

### Reference inputs

- [Shared rules](../../../AGENTS.md), the previous [current status](../status.md),
  affected map cards and the previous accepted handoff.
- [Maintenance instructions](../maintenance.md) for generated indexes and source
  fingerprints. Generated navigation does not accept a research artifact.

## Process

1. Distinguish implementation, publication, CI, capture, verification and source
   integration. Report only observed states, including any failed or pending step.
2. Write a short handoff with the outcome, exact evidence, remaining uncertainty
   and the next actionable task/authority boundary.
3. Update the canonical status router when the current checkpoint or next action
   changes, linking the run product rather than copying its full narrative.
4. Refresh impacted generated indexes and verify links. Preserve original frozen
   evidence and historical checkpoint files; correct stale interpretation through
   a source-linked child note, not a silent rewrite of a frozen parent.

## Outputs

- `runs/<id>/04_handoff.md`, from the
  [handoff template](../_templates/work-item/handoff.md).
- An updated run `CONTEXT.md` with the truthful active/completed/blocked state.
- A concise change to [status.md](../status.md) when warranted, plus necessary map
  and generated-index updates. The status file remains the single current router;
  individual run products preserve what was known at their checkpoint.
- A user-facing summary of the result and any real blocker. Publication is an
  observed external operation, not a conclusion inferred from a local commit.

## Human check

Report completion within the accepted scope without asking for another approval
merely to write the handoff. Ask only for a substantive remaining decision or
new authority. Do not claim the owner accepted a policy, expanded spending or
authorized live trading because an implementation was delivered.

## Do NOT load

- Every run or historical status document to summarize one scoped change.
- Private credentials, full datasets or raw logs that the handoff need only link.
- Unexecuted future work as if it were a finished deliverable.
- All system-map cards merely to update one current-status link.

Next: stop with the completed handoff, or return to
[01_scope](../01_scope/CONTEXT.md) for the next task already within authorization.
