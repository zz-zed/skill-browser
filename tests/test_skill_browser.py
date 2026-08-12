import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "skill-browser"
SCRIPT = SKILL / "scripts" / "skill_browser.py"
SPEC = importlib.util.spec_from_file_location("skill_browser_module", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_skill(root: Path, folder: str, name: str, description: str, body: str = "") -> Path:
    skill_dir = root / folder
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\n{body}\n",
        encoding="utf-8",
    )
    return skill_dir


class SkillBrowserTests(unittest.TestCase):
    def test_release_layout_is_self_discoverable(self):
        inventory = MODULE.scan_skills(
            ROOT,
            extra_roots=[ROOT / "skills"],
            include_self=True,
        )
        record = MODULE.select_skill(inventory, str(SKILL.resolve()))
        self.assertEqual(record["canonical_path"], str(SKILL.resolve()))
        self.assertEqual(record["parse_warnings"], [])
        self.assertTrue(all(reference["exists"] for reference in record["references"]))

    def test_parse_options_and_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            skill = write_skill(
                root,
                "visual-skill",
                "visual-skill",
                "Create visual assets.",
                """## Options

| Option | Values |
|---|---|
| `--style` | clean, bold |

## Layout Gallery

| Layout | Best For |
|---|---|
| `dashboard` | Metrics |
""",
            )
            (skill / "references").mkdir()
            record = MODULE.parse_skill(skill)
            self.assertTrue(record["resources"]["references"])
            sections = {group["section"] for group in record["option_groups"]}
            self.assertEqual(sections, {"Options", "Layout Gallery"})
            self.assertEqual(record["option_groups"][0]["tables"][0]["rows"][0]["Option"], "--style")

    def test_workflow_tool_sections_are_not_options(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            skill = write_skill(
                root,
                "workflow-skill",
                "workflow-skill",
                "Run a workflow.",
                """## Image Generation Tools

- Use one backend.

## Step 4: Confirm Options

- Confirm before execution.

## Options

### Visual Dimensions

| Option | Values |
|---|---|
| `--style` | clean |
""",
            )
            record = MODULE.parse_skill(skill)
            sections = [group["section"] for group in record["option_groups"]]
            self.assertEqual(sections, ["Visual Dimensions"])
            self.assertEqual(record["option_groups"][0]["category"], "visual")

    def test_reference_outside_skill_is_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            skill = write_skill(
                root,
                "safe-skill",
                "safe-skill",
                "Safe Skill.",
                "Read [inside](references/inside.md) and [outside](../../secret.txt).",
            )
            references = skill / "references"
            references.mkdir()
            (references / "inside.md").write_text("inside", encoding="utf-8")
            record = MODULE.parse_skill(skill)
            self.assertTrue(record["references"][0]["exists"])
            self.assertEqual(record["references"][1]["blocked"], "outside-skill-directory")
            self.assertNotIn("path", record["references"][1])

    def test_symlink_locations_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            shared = base / "shared"
            claude = base / "claude"
            physical = write_skill(shared, "shared-skill", "shared-skill", "Shared capability.")
            claude.mkdir()
            (claude / "shared-skill").symlink_to(physical, target_is_directory=True)
            roots = [
                MODULE.RootSpec(shared, "shared", "user", ("codex",)),
                MODULE.RootSpec(claude, "claude", "user", ("claude",)),
            ]
            original = MODULE.default_roots
            MODULE.default_roots = lambda cwd: roots
            try:
                inventory = MODULE.scan_skills(base)
            finally:
                MODULE.default_roots = original
            self.assertEqual(len(inventory["skills"]), 1)
            self.assertEqual(inventory["skills"][0]["hosts"], ["claude", "codex"])
            self.assertEqual(len(inventory["skills"][0]["locations"]), 2)

    def test_same_name_different_paths_is_a_conflict(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = base / "first"
            second = base / "second"
            write_skill(first, "one", "duplicate", "First.")
            write_skill(second, "two", "duplicate", "Second.")
            roots = [
                MODULE.RootSpec(first, "first", "user", ("codex",)),
                MODULE.RootSpec(second, "second", "user", ("codex",)),
            ]
            original = MODULE.default_roots
            MODULE.default_roots = lambda cwd: roots
            try:
                inventory = MODULE.scan_skills(base)
            finally:
                MODULE.default_roots = original
            self.assertEqual(len(inventory["skills"]), 2)
            self.assertEqual(len(inventory["conflicts"]["duplicate"]), 2)
            with self.assertRaises(MODULE.ScanFailure):
                MODULE.select_skill(inventory, "duplicate")

    def test_bad_skill_does_not_break_scan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            write_skill(root, "good", "good", "Good Skill.")
            bad = root / "bad"
            bad.mkdir(parents=True)
            (bad / "SKILL.md").write_bytes(b"\xff\xfe")
            roots = [MODULE.RootSpec(root, "test", "custom", ("codex",))]
            original = MODULE.default_roots
            MODULE.default_roots = lambda cwd: roots
            try:
                inventory = MODULE.scan_skills(Path(temporary))
            finally:
                MODULE.default_roots = original
            self.assertEqual([skill["name"] for skill in inventory["skills"]], ["good"])
            self.assertEqual(len(inventory["warnings"]), 1)

    def test_self_is_excluded_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            write_skill(root, "skill-browser", "skill-browser", "Browse Skills.")
            roots = [MODULE.RootSpec(root, "test", "custom", ("codex",))]
            original = MODULE.default_roots
            MODULE.default_roots = lambda cwd: roots
            try:
                hidden = MODULE.scan_skills(Path(temporary))
                visible = MODULE.scan_skills(Path(temporary), include_self=True)
            finally:
                MODULE.default_roots = original
            self.assertEqual(hidden["skills"], [])
            self.assertEqual(visible["skills"][0]["name"], "skill-browser")

    def test_recommend_is_explicitly_lexical(self):
        record = {
            "name": "diagram-maker",
            "id": "/diagram-maker",
            "description": "Create architecture diagrams.",
            "hosts": ["codex"],
            "sections": [{"title": "Architecture", "line": 1, "level": 2}],
        }
        results = MODULE.search_records({"skills": [record]}, "architecture")
        self.assertEqual(results[0]["name"], "diagram-maker")
        self.assertGreater(results[0]["score"], 0)

    def test_cli_payload_is_json_serializable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            write_skill(root, "sample", "sample", "Sample Skill.")
            inventory = MODULE.scan_skills(Path(temporary), extra_roots=[root])
            json.dumps(inventory, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
