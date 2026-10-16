# 02 — Change

## Inputs

### Working inputs

- `runs/<id>/01_scope.md` and the run router, using the [path notation](../CONTEXT.md).
- The exact editable source, documentation and tests named by that scope.
- Existing user changes in those files, reviewed before any edit.

### Reference inputs

- [Shared rules](../../../AGENTS.md), affected [system-map routes](../../map/CONTEXT.md),
  and only the original contracts needed to preserve the component interface.
- [Current status](../status.md) for the current accepted evidence boundary.

## Process

1. Check that the observed parent and dependencies still match the scope.
2. Make the smallest coherent change and add targeted regression checks. Reuse
   existing tested helpers rather than adding another parallel launcher.
3. Update impacted map/workflow documents when behavior or navigation changes;
   leave unrelated history and source records untouched.
4. Record the diff, implementation decisions and any remaining uncertainty in
   the [change product](../_templates/work-item/change.md). If scope changes,
   return to scope and identify the decision; do not silently expand it.

## Outputs

- The scoped editable code/documentation/test diff, with concrete repository paths.
- `runs/<id>/02_change.md`: implemented changes, intentionally unchanged
  consumers, checks still required, and any observed blockers.
- New versioned child artifacts for research corrections when required by their
  source contract; original captures, sealed manifests and failed evidence are
  never editable outputs. Do not relabel a historical failure as a success.

## Human check

An authorized implementation can proceed directly to verification. Pause for a
new scope/authority decision, an unresolved overlapping user edit, or a proposed
move/deletion with unknown consumers. No new check-in is required for each
isolated code edit, regression test or minor documentation correction.

## Do NOT load

- Every stage's output or every component's source as routine context.
- Outcome labels, recap fills or held-out narratives to tune this change.
- Provider credentials or fresh data unless the separately authorized capture
  workflow requires them and its existing gates are satisfied.
- Frozen records as writable work products, even when their wording is stale.

Next: [03_verify](../03_verify/CONTEXT.md).
