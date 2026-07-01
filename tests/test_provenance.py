"""Tests for passive correction capture (span tracking + scan), no network.

Runs standalone (`python3 tests/test_provenance.py`) and under unittest.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.capture import provenance
from disposition.llm import FakeLLM
from disposition.models import Layer
from disposition.store import Store


def _git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True)


def _make_repo(name: str, content: str) -> str:
    repo = tempfile.mkdtemp()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (pathlib.Path(repo) / name).write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def _store() -> Store:
    store = Store(pathlib.Path(tempfile.mkdtemp()))
    store.scaffold("java")
    return store


_ORIGINAL = "class A {\n    int add(int a, int b) {\n        int r = a + b;\n        return r;\n    }\n}\n"
_EDITED = "class A {\n    int add(int a, int b) {\n        return a + b;\n    }\n}\n"


class TestRecordSpan(unittest.TestCase):
    def test_record_snapshots_code_and_anchor(self):
        repo = _make_repo("A.java", _ORIGINAL)
        store = _store()
        span = provenance.record_span(store, repo, "A.java", 2, 5)
        self.assertIn("int add", span.ai_code)
        self.assertTrue(span.anchor)  # git blob sha recorded
        self.assertEqual(span.status, "open")
        # Persisted and reloadable.
        self.assertEqual(len(provenance._load_spans(store)), 1)


class TestScan(unittest.TestCase):
    def test_unchanged_span_stays_pending_without_llm(self):
        repo = _make_repo("A.java", _ORIGINAL)
        store = _store()
        provenance.record_span(store, repo, "A.java", 2, 5)
        # An empty FakeLLM would raise if the classifier were called.
        result = provenance.scan(store, repo, llm=FakeLLM([]))
        self.assertEqual((result.corrections, result.pending), (0, 1))

    def test_preserving_edit_becomes_correction(self):
        repo = _make_repo("A.java", _ORIGINAL)
        store = _store()
        provenance.record_span(store, repo, "A.java", 2, 5)
        (pathlib.Path(repo) / "A.java").write_text(_EDITED, encoding="utf-8")

        # reinforce() calls the classifier then the taste-delta rule namer.
        fake = FakeLLM(
            [
                {"preserving": True, "confidence": 0.9, "reason": "same result"},
                {"key": "concise-return", "text": "Return expressions directly."},
            ]
        )
        result = provenance.scan(store, repo, llm=fake)
        self.assertEqual(result.corrections, 1)
        exemplars = store.load_exemplars(Layer.LANGUAGE, "java")
        self.assertTrue(any(e.provenance == "correction" for e in exemplars))
        # Span is resolved, so a second scan does nothing.
        again = provenance.scan(store, repo, llm=FakeLLM([]))
        self.assertEqual(again.corrections, 0)

    def test_behavior_changing_edit_is_excluded(self):
        repo = _make_repo("A.java", _ORIGINAL)
        store = _store()
        provenance.record_span(store, repo, "A.java", 2, 5)
        (pathlib.Path(repo) / "A.java").write_text(
            _ORIGINAL.replace("a + b", "a - b"), encoding="utf-8"
        )
        fake = FakeLLM([{"preserving": False, "confidence": 0.2, "reason": "subtracts"}])
        result = provenance.scan(store, repo, llm=fake)
        self.assertEqual((result.corrections, result.excluded), (0, 1))


if __name__ == "__main__":
    unittest.main()
