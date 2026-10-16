"""Provider-free fixture tests for ICM navigation, contracts and review locks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts import maintain_icm as m


OBJECT = "docs/map/objects/feed.md"
PROCESS = "docs/map/processes/replay.md"


def card(kind, identity, source="src/feed.py:1-2", status="verified"):
    fields = {
        "type": kind, "id": f"{kind}-{identity}", "title": identity.title(), "cluster": "research",
        "universe": "live", "status": status, "verified_at": "2026-10-16",
        "verified_commit": "a" * 40, "entity": "src/feed.py", "sources": [source],
        "consumes": [OBJECT] if kind == "process" else [],
        "produces": [OBJECT] if kind == "process" else [],
    }
    text = "---\n" + "\n".join(f"{key}: {json.dumps(value)}" for key, value in fields.items()) + "\n---\n\n"
    for heading in m.SECTIONS[kind]:
        text += f"## {heading}\n\n"
        text += "Hits: replay.\nDoes not hit: live orders.\n\n" if heading == "If you change this" else "Source-reviewed description.\n\n"
    return text


class IcmWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        self.put("AGENTS.md", "# Start\n\n[Context](CONTEXT.md)\n")
        self.put("CONTEXT.md", "# Root contract\n")
        self.put("CLAUDE.md", "# Start\n\n[Agents](AGENTS.md)\n")
        self.put("docs/map/CLAUDE.md", "# Map\n\n[Objects](objects/_index.md)\n[Processes](processes/_index.md)\n")
        self.put("src/feed.py", "FIRST = 1\nSECOND = 2\n")
        self.put(OBJECT, card("object", "feed"))
        self.put(PROCESS, card("process", "replay"))

    def put(self, path, contents):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")

    def change(self, path, old, new):
        self.put(path, (self.root / path).read_text().replace(old, new))

    def prepare(self):
        m.maintain(self.root, "accept")
        m.maintain(self.root, "write")
        m.maintain(self.root)

    def test_valid_workspace_is_deterministic_and_mirrors_byte_identical(self):
        self.prepare()
        before = {name: (self.root / name).read_bytes() for name in (*m.GENERATED, m.LOCK)}
        m.maintain(self.root, "write")
        m.maintain(self.root)
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in before})
        catalog = (self.root / m.MAP / "CLAUDE.md").read_bytes()
        self.assertEqual(catalog, (self.root / m.MAP / "AGENTS.md").read_bytes())
        self.assertEqual(catalog, (self.root / m.MAP / "routing.md").read_bytes())

    def test_write_never_accepts_changed_sources(self):
        self.prepare()
        original_lock = (self.root / m.LOCK).read_bytes()
        self.put("src/feed.py", "FIRST = 3\nSECOND = 2\n")
        m.maintain(self.root, "write")
        self.assertEqual(original_lock, (self.root / m.LOCK).read_bytes())
        with self.assertRaisesRegex(m.InvalidWorkspace, "reviewed source/card drift"):
            m.maintain(self.root)
        m.maintain(self.root, "accept")
        m.maintain(self.root)

    def test_changed_card_assertion_requires_review(self):
        self.prepare()
        self.change(OBJECT, "Source-reviewed description.", "Changed assertion.")
        with self.assertRaisesRegex(m.InvalidWorkspace, "reviewed source/card drift"):
            m.maintain(self.root)

    def test_verified_revision_changes_require_review(self):
        self.prepare()
        self.change(OBJECT, "a" * 40, "b" * 40)
        with self.assertRaisesRegex(m.InvalidWorkspace, "reviewed source/card drift"):
            m.maintain(self.root)

    def test_generated_drift_rejected(self):
        self.prepare()
        self.put("docs/map/routing.md", "corrupted\n")
        with self.assertRaisesRegex(m.InvalidWorkspace, "generated drift"):
            m.maintain(self.root)

    def test_source_line_bounds_rejected(self):
        self.change(OBJECT, "src/feed.py:1-2", "src/feed.py:1-3")
        with self.assertRaisesRegex(m.InvalidWorkspace, "line bounds"):
            m.maintain(self.root, "accept")

    def test_source_reverse_range_and_missing_file_rejected(self):
        for source in ("src/feed.py:2-1", "missing.py:1", "src/feed.py:0", "src/feed.py"):
            with self.subTest(source=source):
                self.put(OBJECT, card("object", "feed", source=source))
                with self.assertRaises(m.InvalidWorkspace):
                    m.maintain(self.root, "accept")

    def test_missing_owning_entity_rejected(self):
        self.change(OBJECT, 'entity: "src/feed.py"', 'entity: "src/missing.py"')
        with self.assertRaisesRegex(m.InvalidWorkspace, "owning entity is missing"):
            m.maintain(self.root, "accept")

    def test_verified_owning_entity_must_be_cited(self):
        self.put("src/other.py", "OTHER = 1\n")
        self.change(OBJECT, 'entity: "src/feed.py"', 'entity: "src/other.py"')
        with self.assertRaisesRegex(m.InvalidWorkspace, "owning entity must be cited"):
            m.maintain(self.root, "accept")

    def test_owning_entity_cannot_escape_repository(self):
        self.change(OBJECT, 'entity: "src/feed.py"', 'entity: "../outside.py"')
        with self.assertRaisesRegex(m.InvalidWorkspace, "escapes repository"):
            m.maintain(self.root, "accept")

    def test_broken_links_and_escapes_rejected(self):
        for link in ("missing.md", "../outside.md", "/etc/passwd", "file:///etc/passwd", "//example.com/file", "%2e%2e/outside.md"):
            with self.subTest(link=link):
                self.put("AGENTS.md", f"[Bad]({link})\n")
                with self.assertRaises(m.InvalidWorkspace):
                    m.maintain(self.root, "write")

    def test_allowed_external_anchors_and_template_placeholders(self):
        self.put("AGENTS.md", "[Remote](https://example.com/a)\n[Email](mailto:test@example.com)\n[Here](#start)\n[Context](CONTEXT.md#root)\n````\n[Example](missing.md)\n````\n")
        self.put("docs/agent-workflow/_templates/item.md", "[Input]({{source_path}})\n")
        self.prepare()

    def test_reference_links_checked(self):
        self.put("AGENTS.md", "[Broken][source]\n\n[source]: missing.md\n")
        with self.assertRaisesRegex(m.InvalidWorkspace, "broken link"):
            m.maintain(self.root, "write")

    def test_casefold_file_and_directory_collisions(self):
        self.put("Docs/readme.txt", "case collision\n")
        with self.assertRaisesRegex(m.InvalidWorkspace, "case-fold collision"):
            m.maintain(self.root, "write")

    def test_missing_heading_and_impact_boundary_rejected(self):
        self.change(OBJECT, "## Shape", "## Wrong")
        with self.assertRaisesRegex(m.InvalidWorkspace, "missing section"):
            m.maintain(self.root, "write")
        self.put(OBJECT, card("object", "feed").replace("Does not hit", "Omitted boundary"))
        with self.assertRaisesRegex(m.InvalidWorkspace, "Hits and Does not hit"):
            m.maintain(self.root, "write")

    def test_invalid_metadata(self):
        for old, new in (("2026-10-16", "2026-02-30"), ("a" * 40, "abcdef"),
                         ('universe: "live"', 'universe: "dead"'),
                         ('status: "verified"', 'status: "complete"'),
                         ('sources: ["src/feed.py:1-2"]', "sources: []")):
            with self.subTest(new=new):
                self.put(OBJECT, card("object", "feed").replace(old, new))
                with self.assertRaises(m.InvalidWorkspace):
                    m.maintain(self.root, "accept")

    def test_duplicate_id_and_missing_object_reference_rejected(self):
        self.put("docs/map/objects/other.md", card("object", "feed"))
        with self.assertRaisesRegex(m.InvalidWorkspace, "duplicate card id"):
            m.maintain(self.root, "write")
        (self.root / "docs/map/objects/other.md").unlink()
        self.put(PROCESS, card("process", "replay").replace(OBJECT, "docs/map/objects/missing.md"))
        with self.assertRaisesRegex(m.InvalidWorkspace, "unknown object reference"):
            m.maintain(self.root, "write")

    def test_stale_card_is_not_certified_by_accept(self):
        self.put(OBJECT, card("object", "feed", status="stale"))
        m.maintain(self.root, "accept")
        m.maintain(self.root, "write")
        self.assertNotIn(OBJECT, json.loads((self.root / m.LOCK).read_text())["cards"])
        with self.assertRaisesRegex(m.InvalidWorkspace, "stale cards"):
            m.maintain(self.root)

    def test_catalog_line_budget(self):
        for name in ("AGENTS.md", "CONTEXT.md", "CLAUDE.md", "docs/map/CLAUDE.md"):
            with self.subTest(name=name):
                original = (self.root / name).read_text()
                self.put(name, "line\n" * 60)
                with self.assertRaisesRegex(m.InvalidWorkspace, "below 60 lines"):
                    m.maintain(self.root, "write")
                self.put(name, original)

    def test_card_identifiers_require_type_prefix_and_kebab_slug(self):
        for identity in ("feed", "process-feed", "object-Feed", "object-feed_name", "object-feed--name"):
            with self.subTest(identity=identity):
                self.put(OBJECT, card("object", "feed").replace('id: "object-feed"', f'id: "{identity}"'))
                with self.assertRaisesRegex(m.InvalidWorkspace, "prefixed kebab identifier"):
                    m.maintain(self.root, "accept")

    def test_card_filename_requires_kebab_slug(self):
        self.put("docs/map/objects/bad_name.md", card("object", "other"))
        with self.assertRaisesRegex(m.InvalidWorkspace, "filename must be kebab-case"):
            m.maintain(self.root, "accept")

    def test_empty_process_io_allowed_with_explicit_explanation(self):
        original = card("process", "replay")
        for key in ("consumes", "produces", "both"):
            with self.subTest(key=key):
                content = original.replace('entity: "src/feed.py"', 'entity: "src/feed.py"\nunmapped_io: "Legacy input/output is not mapped yet."')
                for field in ("consumes", "produces") if key == "both" else (key,):
                    content = content.replace(f'{field}: ["{OBJECT}"]', f"{field}: []")
                self.put(PROCESS, content)
                self.prepare()

    def test_empty_process_io_requires_nonempty_scalar_explanation(self):
        for reason in (None, '""', '"   "', "[]", '["reason"]'):
            with self.subTest(reason=reason):
                content = card("process", "replay").replace(f'consumes: ["{OBJECT}"]', "consumes: []")
                if reason is not None:
                    content = content.replace('entity: "src/feed.py"', f'entity: "src/feed.py"\nunmapped_io: {reason}')
                self.put(PROCESS, content)
                with self.assertRaisesRegex(m.InvalidWorkspace, "unmapped_io explanation"):
                    m.maintain(self.root, "accept")

    def test_unmapped_io_does_not_allow_missing_array_keys(self):
        for field in ("consumes", "produces"):
            with self.subTest(field=field):
                content = card("process", "replay").replace(f'{field}: ["{OBJECT}"]\n', "")
                content = content.replace('entity: "src/feed.py"', 'entity: "src/feed.py"\nunmapped_io: "Not mapped."')
                self.put(PROCESS, content)
                with self.assertRaisesRegex(m.InvalidWorkspace, "require both consumes and produces"):
                    m.maintain(self.root, "accept")

    def test_unmapped_io_does_not_bypass_nonempty_reference_validation(self):
        content = card("process", "replay").replace(f'consumes: ["{OBJECT}"]', "consumes: []")
        content = content.replace(OBJECT, "docs/map/objects/missing.md")
        content = content.replace('entity: "src/feed.py"', 'entity: "src/feed.py"\nunmapped_io: "Input not mapped."')
        self.put(PROCESS, content)
        with self.assertRaisesRegex(m.InvalidWorkspace, "unknown object reference"):
            m.maintain(self.root, "accept")

    def test_generated_output_symlink_rejected_before_any_write(self):
        self.prepare()
        before = {path: (self.root / path).read_bytes() for path in m.GENERATED}
        source = (self.root / "src/feed.py").read_bytes()
        self.put("docs/map/CLAUDE.md", "# Changed catalog\n")
        target = self.root / "docs/map/FILE-MAP.md"
        target.unlink()
        target.symlink_to(self.root / "src/feed.py")
        with self.assertRaisesRegex(m.InvalidWorkspace, "symlink"):
            m.maintain(self.root, "write")
        self.assertEqual(source, (self.root / "src/feed.py").read_bytes())
        for path in m.GENERATED[:-1]:
            self.assertEqual(before[path], (self.root / path).read_bytes())

    def test_generated_output_parent_symlink_rejected_before_any_write(self):
        (self.root / "docs/map/objects").rename(self.root / "object-storage")
        (self.root / "docs/map/objects").symlink_to(self.root / "object-storage", target_is_directory=True)
        with self.assertRaisesRegex(m.InvalidWorkspace, "symlink"):
            m.maintain(self.root, "write")
        self.assertFalse((self.root / "docs/map/AGENTS.md").exists())
        self.assertFalse((self.root / "object-storage/_index.md").exists())

    def test_source_lock_symlink_rejected_without_source_mutation(self):
        target = self.root / m.LOCK
        target.parent.mkdir(parents=True)
        target.symlink_to(self.root / "src/feed.py")
        before = (self.root / "src/feed.py").read_bytes()
        with self.assertRaisesRegex(m.InvalidWorkspace, "symlink"):
            m.maintain(self.root, "accept")
        self.assertEqual(before, (self.root / "src/feed.py").read_bytes())

    def test_source_lock_parent_symlink_rejected(self):
        (self.root / "docs/map/_meta").symlink_to(self.root / "src", target_is_directory=True)
        with self.assertRaisesRegex(m.InvalidWorkspace, "symlink"):
            m.maintain(self.root, "accept")
        self.assertFalse((self.root / "src/source-lock.json").exists())

    def test_hardlinked_generated_output_and_source_lock_rejected(self):
        for relative, mode in ((m.GENERATED[0], "write"), (m.LOCK, "accept")):
            with self.subTest(relative=relative):
                target = self.root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(self.root / "src/feed.py", target)
                before = (self.root / "src/feed.py").read_bytes()
                with self.assertRaisesRegex(m.InvalidWorkspace, "hardlink aliases"):
                    m.maintain(self.root, mode)
                self.assertEqual(before, (self.root / "src/feed.py").read_bytes())
                target.unlink()

    def test_inventory_includes_tracked_and_untracked_excludes_ignored(self):
        self.put(".gitignore", "ignored/\n")
        self.put("ignored/secret.txt", "not inventoried\n")
        self.put("new.txt", "provisional file\n")
        subprocess.run(["git", "-C", str(self.root), "add", "src/feed.py"], check=True)
        self.prepare()
        file_map = (self.root / m.MAP / "FILE-MAP.md").read_text()
        self.assertIn("`src/feed.py`", file_map)
        self.assertIn("`new.txt`", file_map)
        self.assertNotIn("ignored/secret.txt", file_map)
        self.assertIn("provisional classification", file_map)

    def test_default_check_is_read_only(self):
        self.prepare()
        before = {name: (self.root / name).read_bytes() for name in m.inventory(self.root)}
        m.maintain(self.root)
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in m.inventory(self.root)})

    def test_source_symlink_cannot_escape_repository(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "source.py"
            external.write_text("secret\n")
            (self.root / "src/feed.py").unlink()
            (self.root / "src/feed.py").symlink_to(external)
            with self.assertRaisesRegex(m.InvalidWorkspace, "escapes repository"):
                m.maintain(self.root, "accept")


    def test_preserved_routes_validate_and_detect_tampering(self):
        table = "| Task | Open first | Source of truth |\n|---|---|---|\n| Feed | `src/feed.py` | Source |"
        self.put("docs/map/task-routes.md", "# Preserved routes\n\n" + table + "\n")
        metadata = {"version": 1, "source_commit": "a" * 40, "source_path": "AGENTS.md",
                    "destination": "docs/map/task-routes.md", "route_count": 1,
                    "table_sha256": hashlib.sha256(table.encode()).hexdigest()}
        self.put("docs/map/_meta/routes-provenance.json", json.dumps(metadata))
        self.prepare()
        self.change("docs/map/task-routes.md", "Feed |", "Altered |")
        with self.assertRaisesRegex(m.InvalidWorkspace, "count/hash mismatch"):
            m.maintain(self.root)

    def test_preserved_route_missing_target_rejected_even_with_matching_hash(self):
        table = "| Task | Open first | Source of truth |\n|---|---|---|\n| Feed | `missing.py` | Source |"
        self.put("docs/map/task-routes.md", table + "\n")
        metadata = {"version": 1, "source_commit": "a" * 40, "source_path": "AGENTS.md",
                    "destination": "docs/map/task-routes.md", "route_count": 1,
                    "table_sha256": hashlib.sha256(table.encode()).hexdigest()}
        self.put("docs/map/_meta/routes-provenance.json", json.dumps(metadata))
        with self.assertRaisesRegex(m.InvalidWorkspace, "missing file"):
            m.maintain(self.root, "write")


class IcmRepositoryIntegrationTests(unittest.TestCase):
    def test_repository_navigation_and_reviewed_sources_are_current(self):
        m.maintain(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    unittest.main()
