# System map schema

## Cards and naming

Card types are closed: `object` (noun) and `process` (real movement).
Files are kebab-case under `docs/map/objects/` or `docs/map/processes/`.
Each folder has its own CONTEXT; _index.md files are generated.

Frontmatter is a deliberately small YAML subset: one scalar per line or a JSON
array. No YAML tags, anchors, multiline blocks or executable loading.
Required fields: type, id (globally unique object-/process-prefixed slug), title,
cluster, universe (live/leftover/ghost), status
(stub/verified/stale), entity (repository-relative owning file).
Verified cards additionally need verified_at (ISO date), verified_commit (40 hex),
and nonempty sources: a JSON array of repository-relative `path:start-end` citations.
Both card types name their cluster. Process cards declare consumes and produces as
JSON arrays of repository-relative object-card paths.
Both arrays are required. An empty array is allowed only with a nonempty
`unmapped_io` scalar explaining the boundary; do not invent modern graph edges
for legacy inputs or outputs outside the mapped object set.

Verified means the card was checked against cited code at that revision/date,
not that a strategy is profitable, integrated, promoted or permitted to trade.
A source byte change makes a verified card stale until re-reviewed.
The source lock includes both cited source-file hashes and card text hashes and is
separate from ordinary index generation. It records reviewed claims, not merely paths.

## Required content

Objects: Why this shape; Shape; Connected to; If you change this; Surfaces; See.
Processes: Input → Movement → Output; Why this shape; Steps; If you change this;
Surfaces; See. Every change section names Hits and Does not hit.
Cite actual source lines and link to the owning file, not another essay.
External path consumers are unknown unless confirmed; a missing grep hit is not
proof of absence. No existing path may move on that assumption.

## Generated surfaces

[Maintainer](../../../scripts/maintain_icm.py) generates map catalog twins,
object/process indexes and FILE-MAP.md. Never hand-edit them.
`--accept-reviewed-sources` is a separate explicit action after reading changed
source; `--write` does not recertify cards. `--check` is read-only.
Maintenance preflights every managed output and ancestor, rejecting symlinks,
hardlinks and nonregular destinations before mutation. It atomically replaces
only its declared output files, never truncating an aliased source inode.

FILE-MAP role labels are purpose-based navigation, not deletion permission:
catalog (routes/cards/indexes), contract (rules/stage contracts/registrations),
factory (code/tests/tooling/templates), product (run artifacts and historical
records). Mixed files keep their primary role. No file is automatically Dead.
Root entry files stay below 60 lines. Check relative links, citation ranges,
case-folded collisions, generated drift and verified source hashes.

## Authority

[Root rules](../../../AGENTS.md) own project constraints. Existing code/registrations
own executable semantics. [Status](../../agent-workflow/status.md) owns the latest
observed handoff. Cards and indexes only direct a reader to these owners.
