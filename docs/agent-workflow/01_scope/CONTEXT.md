# 01 — Scope

## Inputs

### Working inputs

- The user's current request and any explicit approval of this work item.
- [Current status](../status.md), the relevant [map routes](../../map/CONTEXT.md),
  and the latest accepted handoff for the same change, if one exists.
- The actual branch/commit and worktree status; preserve unrelated user edits.

### Reference inputs

- [Shared rules](../../../AGENTS.md) and the affected component's source files,
  tests and registered contract. Follow links only where needed to bound scope.
- Source-linked historical evidence when resolving a real discrepancy; previous
  descriptions alone are not proof of the current branch or workflow state.

## Process

1. Identify the concrete problem, current parent and smallest useful deliverable.
2. Trace affected consumers through the map and code. Separate observed
   dependencies, assumptions and unknown external consumers.
3. Name acceptance checks, frozen inputs and excluded changes. Record the
   existing authorization and any decision that would require new authority.
4. Start the run record from the [scope template](../_templates/work-item/scope.md).

## Outputs

- `runs/<id>/CONTEXT.md`: small work-item router, input evidence and active stage.
- `runs/<id>/01_scope.md`: exact scope, parent, impact boundary, acceptance checks
  and authorization decision. See [path notation](../CONTEXT.md).
- No code change, provider launch or policy promotion is implied by writing scope.

## Human check

Proceed within an already-approved bounded scope without adding an approval-only
turn. Ask the owner when a material choice is missing, a protected workflow
blocks work, a move affects unknown consumers, or the task needs authority beyond
the existing request. State the exact decision and why it changes the scope.
The system map is descriptive evidence, not permission to modify its nodes.

## Do NOT load

- The entire route archive, all historical audits or all transcript uploads.
- Evaluation labels or future outcomes for implementation/replay decisions.
- Credentials, unrelated account data or provider payloads merely to draft scope.
- Downstream stage products that do not yet exist. Do not invent completion.

Next: [02_change](../02_change/CONTEXT.md), only after the scope is sufficiently
clear and authority is established.
