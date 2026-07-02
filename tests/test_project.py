"""Tests for the shared PROJECT layer (ADR 0011, ADR 0002).

Builds a throwaway git repo from the checked-in Java fixtures, derives house
style via FakeLLM, round-trips it through the committed .disposition/rules.yaml,
confirms it non-interactively, and asserts the two-key Cascade precedence:
a Confirmed Project rule beats a Confirmed Personal rule on the same key, but a
Provisional Project rule does NOT. No network, no real LLM.

Runs standalone (`python3 tests/test_project.py`) and under unittest discovery.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.llm import FakeLLM
from disposition.models import Layer, Rule, Status
from disposition.project import (
    confirm_project,
    derive_project,
    load_project_rules,
    save_project_rules,
)
from disposition.store import Store

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "java"

# Canned house-style candidates the FakeLLM returns for derive_project.
_CANNED = [
    {
        "key": "brace-style",
        "text": "Opening braces go on the same line.",
        "confidence": 0.9,
        "mechanical": True,
    },
    {
        "key": "error-handling",
        "text": "Wrap checked exceptions in a domain exception.",
        "confidence": 0.7,
        "mechanical": False,
    },
]


def _init_repo(repo: pathlib.Path) -> None:
    """Copy the Java fixtures into `repo` and make one commit."""
    for src in FIXTURES.glob("*.java"):
        shutil.copy(src, repo / src.name)

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    git("init")
    git("config", "user.email", "dev@example.com")
    git("config", "user.name", "Dev")
    git("add", "-A")
    git("commit", "-m", "fixtures")


class ProjectTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self._tmp.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        _init_repo(self.repo)
        self.store = Store(base / "home")
        self.store.scaffold("java")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_derive_save_load_round_trip(self) -> None:
        rules = derive_project(
            self.repo, language="java", llm=FakeLLM([list(_CANNED)])
        )
        # Derived rules are PROJECT-layer and PROVISIONAL (a weak prior).
        self.assertEqual([r.key for r in rules], ["brace-style", "error-handling"])
        self.assertTrue(all(r.layer is Layer.PROJECT for r in rules))
        self.assertTrue(all(r.status is Status.PROVISIONAL for r in rules))

        path = save_project_rules(self.repo, rules)
        # Committed inside the repo, so it travels with the code.
        self.assertEqual(path, self.repo / ".disposition" / "rules.yaml")
        self.assertTrue(path.exists())

        loaded = load_project_rules(self.repo, "java")
        self.assertEqual([r.key for r in loaded], [r.key for r in rules])
        # Layer is forced to PROJECT on load regardless of the file's contents.
        self.assertTrue(all(r.layer is Layer.PROJECT for r in loaded))

    def test_derive_empty_when_no_java(self) -> None:
        empty = tempfile.mkdtemp()
        # No git repo / no *.java -> nothing to mine, fake is never called.
        self.assertEqual(
            derive_project(empty, language="java", llm=FakeLLM([])), []
        )

    def test_confirm_project_auto_confirms_all(self) -> None:
        save_project_rules(
            self.repo,
            derive_project(self.repo, language="java", llm=FakeLLM([list(_CANNED)])),
        )
        result = confirm_project(self.repo, language="java", auto=True)
        self.assertEqual(result, {"confirmed": 2})

        loaded = load_project_rules(self.repo, "java")
        self.assertTrue(all(r.status is Status.CONFIRMED for r in loaded))

    def test_confirmed_project_beats_confirmed_personal(self) -> None:
        # A developer's own Confirmed Personal rule on the same key.
        self.store.save_rules(
            Layer.PERSONAL,
            [
                Rule(
                    key="brace-style",
                    text="personal preference",
                    status=Status.CONFIRMED,
                    layer=Layer.PERSONAL,
                )
            ],
        )
        save_project_rules(
            self.repo,
            [
                Rule(
                    key="brace-style",
                    text="house style",
                    status=Status.CONFIRMED,
                    layer=Layer.PROJECT,
                )
            ],
        )
        style = {r.key: r for r in self.store.active_style("java", repo=self.repo)}
        # Same status -> the more specific Project layer wins.
        self.assertEqual(style["brace-style"].layer, Layer.PROJECT)
        self.assertEqual(style["brace-style"].text, "house style")

    def test_provisional_project_does_not_beat_confirmed_personal(self) -> None:
        self.store.save_rules(
            Layer.PERSONAL,
            [
                Rule(
                    key="brace-style",
                    text="personal preference",
                    status=Status.CONFIRMED,
                    layer=Layer.PERSONAL,
                )
            ],
        )
        save_project_rules(
            self.repo,
            [
                Rule(
                    key="brace-style",
                    text="house style",
                    status=Status.PROVISIONAL,
                    layer=Layer.PROJECT,
                )
            ],
        )
        style = {r.key: r for r in self.store.active_style("java", repo=self.repo)}
        # Confirmation status is the first precedence key: Confirmed Personal
        # outranks the Provisional Project rule despite Project being specific.
        self.assertEqual(style["brace-style"].layer, Layer.PERSONAL)
        self.assertEqual(style["brace-style"].text, "personal preference")


if __name__ == "__main__":
    unittest.main(verbosity=2)
