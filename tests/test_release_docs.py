import re
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README_EN = ROOT / "README.md"
README_ZH = ROOT / "README.zh-CN.md"
ILLUSTRATIONS = (
    "illustrations/01-infographic-skill-browser-overview.png",
    "illustrations/02-infographic-live-scan-evidence.png",
    "illustrations/03-infographic-trust-boundary.png",
)


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as source:
        header = source.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"not a PNG: {path}")
    return struct.unpack(">II", header[16:24])


class ReleaseDocumentationTests(unittest.TestCase):
    def test_english_is_default_and_language_navigation_is_reciprocal(self):
        english = README_EN.read_text(encoding="utf-8")
        chinese = README_ZH.read_text(encoding="utf-8")
        language_nav = "[English](README.md) | [简体中文](README.zh-CN.md)"
        self.assertIn(language_nav, english)
        self.assertIn(language_nav, chinese)

    def test_mit_license_is_linked_from_both_readmes(self):
        english = README_EN.read_text(encoding="utf-8")
        chinese = README_ZH.read_text(encoding="utf-8")
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        badge = "[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)"
        self.assertIn(badge, english)
        self.assertIn(badge, chinese)
        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright (c) 2026 zz-zed", license_text)

    def test_bilingual_readmes_share_structure_and_commands(self):
        english = README_EN.read_text(encoding="utf-8")
        chinese = README_ZH.read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^## ", english, flags=re.MULTILINE)), 11)
        self.assertEqual(len(re.findall(r"^## ", chinese, flags=re.MULTILINE)), 11)
        self.assertEqual(english.count("```"), chinese.count("```"))
        for command in (
            "npx skills add zz-zed/skill-browser",
            "python3 skills/skill-browser/scripts/skill_browser.py",
            "agentskills validate skills/skill-browser",
            "npx skills add . --list",
        ):
            self.assertIn(command, english)
            self.assertIn(command, chinese)

    def test_readme_illustrations_exist_and_are_landscape_pngs(self):
        english = README_EN.read_text(encoding="utf-8")
        chinese = README_ZH.read_text(encoding="utf-8")
        for relative_path in ILLUSTRATIONS:
            self.assertIn(relative_path, english)
            self.assertIn(relative_path, chinese)
            path = ROOT / relative_path
            self.assertTrue(path.is_file())
            width, height = png_size(path)
            self.assertGreater(width, height)
            self.assertGreaterEqual(width, 1200)

    def test_public_examples_use_fictional_skill_names(self):
        english = README_EN.read_text(encoding="utf-8")
        chinese = README_ZH.read_text(encoding="utf-8")
        for fictional_name in ("diagram-skill", "architecture-skill"):
            self.assertIn(fictional_name, english)
            self.assertIn(fictional_name, chinese)
        self.assertIn("Examples use fictional Skill names", english)
        self.assertIn("所有示例均使用虚构 Skill 名称", chinese)


if __name__ == "__main__":
    unittest.main()
