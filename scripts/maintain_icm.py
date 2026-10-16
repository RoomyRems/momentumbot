#!/usr/bin/env python3
"""Provider-free, deterministic maintenance for the additive ICM documentation map.

--write generates navigation only; it never certifies reviewed sources. Source
locks change only with the separate --accept-reviewed-sources review action.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit


MAP = Path("docs/map")
LOCK = MAP / "_meta/source-lock.json"
GENERATED = (MAP / "AGENTS.md", MAP / "routing.md", MAP / "objects/_index.md",
             MAP / "processes/_index.md", MAP / "FILE-MAP.md")
REQUIRED = ("type", "id", "title", "cluster", "universe", "status", "entity", "sources")
SECTIONS = {
    "object": ("Why this shape", "Shape", "Connected to", "If you change this", "Surfaces", "See"),
    "process": ("Input → Movement → Output", "Why this shape", "Steps", "If you change this", "Surfaces", "See"),
}
CITATION = re.compile(r"^(.+):(\d+)(?:-(\d+))?$")
LINK = re.compile(r"\[[^\]\n]*\]\(([^)\n]*)\)")
REFERENCE = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s*(\S+)", re.MULTILINE)


class InvalidWorkspace(ValueError):
    """A reviewable documentation invariant failed."""


def fail(message: str) -> None:
    raise InvalidWorkspace(message)


def safe_path(root: Path, value: str, *, relative_to: Path | None = None) -> Path:
    if not value or "\\" in value or PurePosixPath(value).is_absolute() or re.match(r"^[A-Za-z]:", value):
        fail(f"unsafe repository path: {value!r}")
    path = (root / (relative_to or Path()) / value).resolve()
    if not path.is_relative_to(root.resolve()):
        fail(f"path escapes repository: {value!r}")
    return path


def validate_outputs(root: Path, outputs) -> None:
    """Reject aliases before any output is created or replaced, including parents."""
    for relative in outputs:
        target = root
        for index, part in enumerate(relative.parts):
            target /= part
            try:
                info = target.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode):
                fail(f"managed output path contains a symlink: {target.relative_to(root)}")
            final = index == len(relative.parts) - 1
            if final:
                if not stat.S_ISREG(info.st_mode):
                    fail(f"managed output is not a regular file: {relative}")
                if info.st_nlink != 1:
                    fail(f"managed output has hardlink aliases: {relative}")
            elif not stat.S_ISDIR(info.st_mode):
                fail(f"managed output parent is not a directory: {target.relative_to(root)}")


def write_outputs(root: Path, outputs: dict[Path, bytes]) -> None:
    # Validate the entire batch before the first mutation; never open an output
    # inode for truncation. Replacement also avoids following a final-file alias.
    validate_outputs(root, outputs)
    for relative, contents in outputs.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".icm-", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(contents)
                stream.flush()
                os.fchmod(stream.fileno(), 0o644)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def inventory(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True, capture_output=True,
    )
    files = sorted(set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) - {""})
    seen: dict[str, str] = {}
    for name in files:
        path = safe_path(root, name)
        if not path.is_file():
            fail(f"tracked or listed file is missing: {name}")
        for count in range(1, len(PurePosixPath(name).parts) + 1):
            prefix = "/".join(PurePosixPath(name).parts[:count])
            key = prefix.casefold()
            if key in seen and seen[key] != prefix:
                fail(f"case-fold collision: {seen[key]} and {prefix}")
            seen[key] = prefix
    return files


def read_card(root: Path, name: str) -> dict:
    content = (root / name).read_text(encoding="utf-8")
    lines = content.splitlines()
    if not lines or lines[0] != "---":
        fail(f"{name}: missing frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError:
        fail(f"{name}: unterminated frontmatter")
    data: dict = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not separator or not re.fullmatch(r"[a-z_]+", key) or key in data:
            fail(f"{name}: invalid/duplicate frontmatter field: {line}")
        if value.startswith("[") or value.startswith('"'):
            try:
                data[key] = json.loads(value)
            except json.JSONDecodeError as exc:
                fail(f"{name}: invalid JSON field {key}: {exc}")
        elif value.startswith("'") and value.endswith("'"):
            data[key] = value[1:-1].replace("''", "'")
        else:
            data[key] = value
    missing = [key for key in REQUIRED if key not in data]
    if missing:
        fail(f"{name}: missing fields: {', '.join(missing)}")
    for key in ("type", "id", "title", "cluster", "universe", "status", "entity"):
        if not isinstance(data[key], str) or not data[key].strip():
            fail(f"{name}: {key} must be a nonempty scalar")
    expected_type = "object" if "/objects/" in name else "process"
    if data["type"] != expected_type:
        fail(f"{name}: expected type {expected_type}")
    slug = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
    if not re.fullmatch(expected_type + "-" + slug, data["id"]):
        fail(f"{name}: id must be a {expected_type}-prefixed kebab identifier")
    if not re.fullmatch(slug + r"\.md", Path(name).name):
        fail(f"{name}: card filename must be kebab-case")
    if data["universe"] not in {"live", "leftover", "ghost"}:
        fail(f"{name}: invalid universe")
    if data["status"] not in {"stub", "verified", "stale"}:
        fail(f"{name}: invalid status")
    if expected_type == "process" and any(key not in data for key in ("consumes", "produces")):
        fail(f"{name}: processes require both consumes and produces array fields")
    for key in ("sources", "consumes", "produces"):
        value = data.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            fail(f"{name}: {key} must be a JSON array of nonempty strings")
        if len(value) != len(set(value)):
            fail(f"{name}: duplicate {key}")
        data[key] = value
    if expected_type == "process" and not (data["consumes"] and data["produces"]):
        reason = data.get("unmapped_io", "")
        if not isinstance(reason, str) or not reason.strip():
            fail(f"{name}: empty process I/O requires a nonempty scalar unmapped_io explanation")
    body = "\n".join(lines[end + 1:])
    headings = set(re.findall(r"^#{2,6}\s+(.+?)\s*$", body, re.MULTILINE))
    for heading in SECTIONS[expected_type]:
        if heading not in headings:
            fail(f"{name}: missing section {heading!r}")
    change = re.search(r"^## If you change this\s*\n(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL)
    if not change or not all(label in change.group(1) for label in ("Hits", "Does not hit")):
        fail(f"{name}: change impact must include Hits and Does not hit")
    if data["status"] in {"verified", "stale"}:
        if not data["sources"]:
            fail(f"{name}: reviewed cards need source citations")
        stamp = data.get("verified_at", "")
        try:
            if not isinstance(stamp, str) or date.fromisoformat(stamp).isoformat() != stamp:
                raise ValueError
        except ValueError:
            fail(f"{name}: verified_at must be an ISO calendar date")
        revision = data.get("verified_commit", "")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            fail(f"{name}: verified_commit must be a full lowercase commit SHA")
    data["path"], data["body"] = name, body
    return data


def citation_file(root: Path, citation: str) -> Path:
    match = CITATION.fullmatch(citation)
    if not match:
        fail(f"invalid source citation: {citation}")
    name, start, end = match.groups()
    path = safe_path(root, name)
    if not path.is_file():
        fail(f"missing source citation file: {citation}")
    try:
        line_count = len(path.read_text(encoding="utf-8").splitlines())
    except UnicodeDecodeError:
        fail(f"source citation must refer to a UTF-8 text file: {citation}")
    if not 1 <= int(start) <= int(end or start) <= line_count:
        fail(f"source citation line bounds invalid: {citation} ({line_count} lines)")
    return path


def cards(root: Path, files: list[str]) -> list[dict]:
    names = [name for name in files if re.fullmatch(r"docs/map/(objects|processes)/[^/]+\.md", name)
             and Path(name).name not in {"CONTEXT.md", "_index.md"}]
    result = [read_card(root, name) for name in names]
    identities: set[str] = set()
    objects = {card["path"] for card in result if card["type"] == "object"}
    for card in result:
        if card["id"] in identities:
            fail(f"duplicate card id: {card['id']}")
        identities.add(card["id"])
        entity = safe_path(root, card["entity"])
        if not entity.is_file():
            fail(f"{card['path']}: owning entity is missing: {card['entity']}")
        cited_files = {citation_file(root, citation) for citation in card["sources"]}
        if card["status"] == "verified" and entity not in cited_files:
            fail(f"{card['path']}: verified owning entity must be cited: {card['entity']}")
        for name in card["consumes"] + card["produces"]:
            safe_path(root, name)
            if name not in objects:
                fail(f"{card['path']}: unknown object reference: {name}")
    return result


def markdown_links(root: Path, files: list[str], *, allow_pending: bool = False) -> None:
    for name in files:
        if not name.endswith(".md") or not (name in {"AGENTS.md", "CONTEXT.md", "CLAUDE.md"}
                or name.startswith(("docs/map/", "docs/agent-workflow/"))):
            continue
        # Templates intentionally contain unreplaced placeholders, not live routes.
        if "_templates" in Path(name).parts:
            continue
        visible, fence = [], ""
        for line in (root / name).read_text(encoding="utf-8").splitlines():
            marker = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
            if marker:
                if not fence:
                    fence = marker.group(1)
                elif marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence) and not marker.group(2).strip():
                    fence = ""
                continue
            if not fence:
                visible.append(re.sub(r"(`+).*?\1", "", line))
        content = "\n".join(visible)
        destinations = LINK.findall(content) + REFERENCE.findall(content)
        for destination in destinations:
            destination = destination.strip()
            if destination.startswith("<"):
                destination = destination.partition(">")[0][1:]
            else:
                destination = destination.split(' "', 1)[0].split(" '", 1)[0]
            parsed = urlsplit(destination)
            if parsed.scheme in {"http", "https", "mailto"} or destination.startswith("#"):
                continue
            if parsed.scheme or parsed.netloc:
                fail(f"{name}: unsupported/absolute link: {destination}")
            target = safe_path(root, unquote(parsed.path), relative_to=Path(name).parent)
            if allow_pending and target.relative_to(root.resolve()) in {*GENERATED, LOCK}:
                continue
            if not target.exists():
                fail(f"{name}: broken link: {destination}")


def classification(name: str) -> tuple[str, str]:
    path = PurePosixPath(name)
    if path.name == "CONTEXT.md":
        return "contract", "folder contract"
    if "_templates" in path.parts:
        return "factory", "reusable template"
    if name in {"AGENTS.md", "CLAUDE.md", "README.md"} or name.startswith("docs/map/") and "/_meta/" not in name:
        return "catalog", "navigation, index or system-map card"
    if name.startswith("docs/map/_meta/"):
        return "contract", "map evidence and schema"
    if name.startswith(("docs/research/", "docs/strategy/", "research/strategy/")):
        return "contract", "research or strategy specification"
    if name.startswith(("src/", "scripts/", "tests/", ".github/", "config/", "configs/",
                        "research/rules/", "research/reference/")) or path.name.startswith("requirements") or name in {"pyproject.toml", "setup.cfg", "setup.py", ".gitignore"}:
        return "factory", "implementation, verification or configuration"
    if name.startswith(("research/data-audits/", "research/runtime/", "research/frozen/", "research/benchmarks/",
                        "research/reference_days/", "docs/project/", "docs/agent-workflow/runs/")):
        return "product", "retained evidence or checkpoint"
    if name.startswith("docs/agent-workflow/"):
        return "contract", "development workflow specification"
    if name.startswith("docs/"):
        return "contract", "explanatory specification"
    return "product", "provisional classification; human review required"


def escaped(value: str) -> str:
    return value.replace("|", "&#124;").replace("\n", " ")


def generated_contents(root: Path, files: list[str], reviewed_cards: list[dict]) -> dict[Path, bytes]:
    catalog = (root / MAP / "CLAUDE.md").read_bytes()
    outputs = {MAP / "AGENTS.md": catalog, MAP / "routing.md": catalog}
    for kind, plural in (("object", "objects"), ("process", "processes")):
        lines = [f"# {plural.title()} index", "", "Generated by `python scripts/maintain_icm.py --write`; do not edit.", "",
                 "| Card | Cluster | Universe | Status | Verified |", "|---|---|---|---|---|"]
        for card in reviewed_cards:
            if card["type"] == kind:
                lines.append(f"| [{escaped(card['title'])}]({Path(card['path']).name}) | {escaped(card['cluster'])} | {card['universe']} | {card['status']} | {card.get('verified_at', '—')} |")
        outputs[MAP / plural / "_index.md"] = ("\n".join(lines) + "\n").encode()
    lines = ["# Repository file map", "", "Generated from all Git-tracked and nonignored new files; no files are moved.",
             "Classification is navigational, never deletion authority. Provisional rows need human review; nothing is automatically Dead.", "",
             "| File | ICM role | Basis |", "|---|---|---|"]
    for name in sorted(set(files) | {str(path) for path in GENERATED} | {str(LOCK)}):
        role, basis = classification(name)
        lines.append(f"| `{escaped(name)}` | {role} | {basis} |")
    outputs[MAP / "FILE-MAP.md"] = ("\n".join(lines) + "\n").encode()
    return outputs


def source_lock(root: Path, reviewed_cards: list[dict]) -> dict:
    result: dict = {"version": 1, "cards": {}}
    for card in reviewed_cards:
        if card["status"] != "verified":
            continue
        sources = {}
        for citation in card["sources"]:
            path = citation_file(root, citation)
            sources[path.relative_to(root.resolve()).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        result["cards"][card["path"]] = {
            "verified_commit": card["verified_commit"], "verified_at": card["verified_at"],
            "card_sha256": hashlib.sha256((root / card["path"]).read_bytes()).hexdigest(),
            "sources": sources,
        }
    return result


def validate_preserved_routes(root: Path) -> None:
    provenance = root / MAP / "_meta/routes-provenance.json"
    if not provenance.exists():
        return
    try:
        metadata = json.loads(provenance.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid route provenance: {exc}")
    if not isinstance(metadata, dict) or metadata.get("version") != 1:
        fail("invalid route provenance version")
    for key, pattern in (("source_commit", r"[0-9a-f]{40}"), ("table_sha256", r"[0-9a-f]{64}")):
        if not isinstance(metadata.get(key), str) or not re.fullmatch(pattern, metadata[key]):
            fail(f"invalid route provenance {key}")
    for key in ("source_path", "destination"):
        if not isinstance(metadata.get(key), str):
            fail(f"invalid route provenance {key}")
        safe_path(root, metadata[key])
    expected_count = metadata.get("route_count")
    if type(expected_count) is not int or expected_count <= 0:
        fail("invalid route provenance route_count")
    target = safe_path(root, metadata["destination"])
    if not target.is_file():
        fail("preserved route destination is missing")
    lines = target.read_text(encoding="utf-8").splitlines()
    header = "| Task | Open first | Source of truth |"
    starts = [index for index, line in enumerate(lines) if line.strip() == header]
    if len(starts) != 1:
        fail("preserved routes must contain exactly one task table")
    table = []
    for line in lines[starts[0]:]:
        if not line.strip().startswith("|"):
            break
        table.append(line)
    digest = hashlib.sha256("\n".join(table).strip().encode("utf-8")).hexdigest()
    if len(table) - 2 != expected_count or digest != metadata["table_sha256"]:
        fail("preserved route table count/hash mismatch")
    for row in table[2:]:
        cells = row.split("|")
        if len(cells) != 5:
            fail("preserved route table has invalid columns")
        paths = re.findall(r"`([^`]+)`", cells[2])
        if not paths:
            fail("preserved route lacks an Open first path")
        for name in paths:
            if not safe_path(root, name).is_file():
                fail(f"preserved route points to missing file: {name}")


def validate_structure(root: Path, files: list[str], *, allow_pending: bool = False) -> list[dict]:
    for name in ("AGENTS.md", "CONTEXT.md", "CLAUDE.md", "docs/map/CLAUDE.md"):
        if not (root / name).is_file():
            fail(f"missing entry point: {name}")
    for name in ("AGENTS.md", "CONTEXT.md", "CLAUDE.md", "docs/map/CLAUDE.md"):
        if len((root / name).read_text(encoding="utf-8").splitlines()) >= 60:
            fail(f"{name}: catalog must stay below 60 lines")
    reviewed_cards = cards(root, files)
    if not reviewed_cards:
        fail("no system-map cards found")
    validate_preserved_routes(root)
    markdown_links(root, files, allow_pending=allow_pending)
    return reviewed_cards


def maintain(root: Path, mode: str = "check") -> None:
    root = root.resolve()
    validate_outputs(root, (*GENERATED, LOCK))
    files = inventory(root)
    reviewed_cards = validate_structure(root, files, allow_pending=mode != "check")
    if mode == "accept":
        # This intentionally explicit action must follow a human/source review.
        payload = json.dumps(source_lock(root, reviewed_cards), indent=2, sort_keys=True) + "\n"
        write_outputs(root, {LOCK: payload.encode("utf-8")})
        return
    outputs = generated_contents(root, files, reviewed_cards)
    if mode == "write":
        write_outputs(root, outputs)
        return
    for path, expected in outputs.items():
        if not (root / path).is_file() or (root / path).read_bytes() != expected:
            fail(f"generated drift: {path}; run --write")
    if any(card["status"] == "stale" for card in reviewed_cards):
        fail("stale cards require source review before verification")
    try:
        recorded = json.loads((root / LOCK).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"missing/invalid source lock: {exc}; review sources before --accept-reviewed-sources")
    if recorded != source_lock(root, reviewed_cards):
        fail("reviewed source/card drift; review affected sources before --accept-reviewed-sources")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="validate without writing (default)")
    action.add_argument("--write", action="store_true", help="regenerate navigation only; then run --check")
    action.add_argument("--accept-reviewed-sources", action="store_true", help="explicitly record reviewed card/source hashes only")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    mode = "accept" if args.accept_reviewed_sources else "write" if args.write else "check"
    try:
        maintain(args.root, mode)
    except (InvalidWorkspace, OSError, subprocess.CalledProcessError) as exc:
        print(f"ICM: {exc}", file=sys.stderr)
        return 1
    messages = {"check": "ICM checks passed.", "write": "ICM navigation regenerated; source review locks unchanged. Run --check.",
                "accept": "ICM reviewed-source lock recorded explicitly. Run --write and --check."}
    print(messages[mode])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
