# 03 — Verify

## Inputs

### Working inputs

- `runs/<id>/01_scope.md`, `runs/<id>/02_change.md`, the actual diff and the
  acceptance checks they specify; see [path notation](../CONTEXT.md).
- The changed source/tests and exact local or hosted outputs needed to evaluate
  those checks. Record the code identity for every result.

### Reference inputs

- [Shared verification rules](../../../AGENTS.md), affected component contracts
  and [maintenance commands](../maintenance.md).
- The existing workflow definition for any CI, capture or independent-verifier
  result being assessed; its job names and success criteria remain authoritative.

## Process

1. Review the diff for intended impact and frozen-input preservation. Run focused
   local tests and optimized-mode checks for new safety gates where applicable.
2. Run the ICM navigation/drift checks for changed map or workflow content. Cold
   walk an affected route from a small entry slice, locating the source, consumer
   boundary and next step without loading the full repository. Name the slice
   and what the walk actually established; this is not a new full replay.
3. Use one authoritative full GitHub CI run for the published code checkpoint,
   following the existing streamlined process. Do not duplicate the whole suite
   locally. Before a provider job or policy promotion, verify successful CI for
   its exact code commit and every additional existing gate.
4. Record observed pass, fail, skip, interruption and unknown states separately.
   A queued job is not a pass; successful capture is not source integration or
   strategy acceptance. Diagnose failures within scope and return to change as
   needed, retaining the failed result.

## Outputs

- `runs/<id>/03_verification.md`, from the
  [verification template](../_templates/work-item/verification.md), with commands,
  code identity, actual results and exact evidence links/paths.
- Original test logs and CI/job/artifact references where available. A concise
  record may link existing immutable evidence instead of duplicating it.
- Explicit unresolved acceptance items, including unavailable external consumers
  or tests not executed. No claim of a completed run without saved evidence.

## Human check

Routine checks, diagnostic cold walks and already-authorized automatic jobs do
not require a new approval turn. Escalate a blocked authority gate, expanded
dataset/spending need or proposed acceptance of a material unresolved failure.
Expired or consumed capture authorization is not renewed by this stage.

## Do NOT load

- The entire historical suite's evidence when a focused check answers the issue.
- Secrets into the report or unrestricted provider payloads into agent context.
- Retrospective labels before the required frozen runtime artifact boundary.
- Downstream results to make a failing acceptance check appear successful.

Next: [04_handoff](../04_handoff/CONTEXT.md), with incomplete items stated plainly.
