# ICM adoption record

Inputs: owner-approved [migration](../../../map/_meta/adoption.md), unchanged source baseline.
Process: inventory/approval → catalog cold walk → source cards → impact index → verification.
Outputs: [scope](01_scope.md), [change](02_change.md), [verification](03_verification.md),
[handoff](04_handoff.md), and [capture metadata](capture-terminal.json).
Human check: confirm no runtime or immutable evidence changes and read the final verification.

Stage files carry status; pending or failed evidence is never promoted by its presence.
