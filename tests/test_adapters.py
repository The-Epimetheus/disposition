"""Tests for the Claude Code adapter (Forced Injection + MCP registration).

Pure stdlib + a temp store/repo. No network, no LLM, no tree-sitter. Runs via
`python3 tests/test_adapters.py` and under unittest discover.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.adapters.claude_code import (
    END_MARKER,
    START_MARKER,
    generate_claude_md_section,
    register_mcp,
    write_claude_md,
)
from disposition.models import Layer, Rule, Status
from disposition.store import Store


def _store_with_rules(root: pathlib.Path) -> Store:
    store = Store(root)
    store.scaffold("java")
    store.save_rules(
        Layer.LANGUAGE,
        [
            Rule(
                key="early-returns",
                text="Prefer guard clauses over nested conditionals.",
                status=Status.CONFIRMED,
                layer=Layer.LANGUAGE,
                confidence=0.9,
            ),
            Rule(
                key="naming",
                text="Use full words, never abbreviations, for identifiers.",
                status=Status.PROVISIONAL,
                layer=Layer.LANGUAGE,
                confidence=0.6,
            ),
        ],
        language="java",
    )
    return store


class GenerateSectionTest(unittest.TestCase):
    def test_contains_rule_text_and_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_with_rules(pathlib.Path(tmp))
            section = generate_claude_md_section(store, language="java")
            self.assertIn(START_MARKER, section)
            self.assertIn(END_MARKER, section)
            self.assertIn("Prefer guard clauses over nested conditionals.", section)
            self.assertIn("early-returns", section)
            # Provisional rules are flagged so their weight is legible.
            self.assertIn("_(provisional)_", section)

    def test_empty_store_still_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(pathlib.Path(tmp))
            store.scaffold("java")
            section = generate_claude_md_section(store, language="java")
            self.assertIn(START_MARKER, section)
            self.assertIn("No style rules captured yet", section)


class WriteClaudeMdTest(unittest.TestCase):
    def test_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_with_rules(pathlib.Path(tmp))
            section = generate_claude_md_section(store, language="java")
            path = write_claude_md(section, repo=tmp)
            self.assertTrue(path.exists())
            self.assertIn("early-returns", path.read_text(encoding="utf-8"))

    def test_idempotent_replace_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_with_rules(pathlib.Path(tmp))
            # Seed CLAUDE.md with user content that must survive both writes.
            claude = pathlib.Path(tmp) / "CLAUDE.md"
            claude.write_text("# Project\n\nHand-written notes.\n", encoding="utf-8")

            first = generate_claude_md_section(store, language="java")
            write_claude_md(first, repo=tmp)
            second = generate_claude_md_section(store, language="java")
            write_claude_md(second, repo=tmp)

            text = claude.read_text(encoding="utf-8")
            # Exactly one marked block: no duplication on re-run.
            self.assertEqual(text.count(START_MARKER), 1)
            self.assertEqual(text.count(END_MARKER), 1)
            # User content is preserved.
            self.assertIn("Hand-written notes.", text)
            self.assertIn("early-returns", text)

    def test_replace_updates_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_with_rules(pathlib.Path(tmp))
            write_claude_md(
                generate_claude_md_section(store, language="java"), repo=tmp
            )
            # Change the rules, regenerate, and confirm the old text is gone.
            store.save_rules(
                Layer.LANGUAGE,
                [
                    Rule(
                        key="immutability",
                        text="Default to final fields and immutable data.",
                        status=Status.CONFIRMED,
                        layer=Layer.LANGUAGE,
                    )
                ],
                language="java",
            )
            write_claude_md(
                generate_claude_md_section(store, language="java"), repo=tmp
            )
            text = (pathlib.Path(tmp) / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("Default to final fields and immutable data.", text)
            self.assertNotIn("early-returns", text)
            self.assertEqual(text.count(START_MARKER), 1)


class RegisterMcpTest(unittest.TestCase):
    def test_default_command(self):
        self.assertEqual(
            register_mcp(),
            ["claude", "mcp", "add", "disposition", "--", "disposition", "serve"],
        )

    def test_custom_name(self):
        self.assertEqual(
            register_mcp(name="taste")[3],
            "taste",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
