"""Tests for Ambient Capture (incremental mining of new commits), no network."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.capture import ambient
from disposition.models import Layer
from disposition.store import Store

_CLASS = (
    "class Widget {\n"
    "    private int size;\n"
    "    int size() { return size; }\n"
    "    void grow() { size = size + 1; }\n"
    "}\n"
)


def _git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True)


def _make_repo() -> str:
    repo = tempfile.mkdtemp()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (pathlib.Path(repo) / "Widget.java").write_text(_CLASS, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def _store() -> Store:
    store = Store(pathlib.Path(tempfile.mkdtemp()))
    store.scaffold("java")
    return store


class TestAmbient(unittest.TestCase):
    def test_first_run_sets_baseline_and_captures_nothing(self):
        repo = _make_repo()
        store = _store()
        result = ambient.capture(store, repo)
        self.assertTrue(result.baseline)
        self.assertEqual(result.exemplars_added, 0)
        self.assertEqual(len(store.load_exemplars(Layer.LANGUAGE, "java")), 0)

    def test_second_run_captures_new_commits(self):
        repo = _make_repo()
        store = _store()
        ambient.capture(store, repo)  # baseline

        # A new commit adds authored Java.
        (pathlib.Path(repo) / "Gauge.java").write_text(
            "class Gauge {\n    double read() { return 1.0; }\n}\n", encoding="utf-8"
        )
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "add gauge")

        result = ambient.capture(store, repo)
        self.assertFalse(result.baseline)
        self.assertGreaterEqual(result.commits, 1)
        self.assertGreater(result.exemplars_added, 0)
        exemplars = store.load_exemplars(Layer.LANGUAGE, "java")
        self.assertTrue(all(e.provenance == "ambient" for e in exemplars))

    def test_no_new_commits_adds_nothing(self):
        repo = _make_repo()
        store = _store()
        ambient.capture(store, repo)  # baseline
        result = ambient.capture(store, repo)  # nothing new since
        self.assertEqual(result.exemplars_added, 0)


if __name__ == "__main__":
    unittest.main()
