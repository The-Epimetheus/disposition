"""Tests for repo bootstrap (ADR 0005): mine Java exemplars + build the index.

Builds a throwaway git repo from the checked-in fixtures, runs bootstrap(),
and asserts exemplars were stored and a VectorIndex was saved and reloads. No
network, no LLM (bootstrap is purely git + LocalEmbedder). Runs via
`python3 tests/test_bootstrap.py` and under unittest discover.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.capture.bootstrap import BootstrapResult, bootstrap
from disposition.embeddings import LocalEmbedder
from disposition.index import VectorIndex
from disposition.models import Layer
from disposition.store import Store

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "java"


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


class BootstrapTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self._tmp.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        self.home = base / "home"
        _init_repo(self.repo)
        self.store = Store(self.home)
        self.store.scaffold("java")
        self.embedder = LocalEmbedder(dim=64)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_bootstrap_adds_exemplars_and_index(self) -> None:
        result = bootstrap(
            self.store, str(self.repo), language="java", embedder=self.embedder
        )
        self.assertIsInstance(result, BootstrapResult)
        # Three fixture files scanned; several methods chunked out of them.
        self.assertEqual(result.files_scanned, 3)
        self.assertGreater(result.exemplars_added, 0)
        self.assertEqual(result.index_size, result.exemplars_added)

        # Exemplars persisted to the LANGUAGE layer with bootstrap provenance.
        stored = self.store.load_exemplars(Layer.LANGUAGE, "java")
        self.assertEqual(len(stored), result.exemplars_added)
        self.assertTrue(all(ex.provenance == "bootstrap" for ex in stored))
        self.assertTrue(all(ex.source.endswith(".java") for ex in stored))

        # Index was saved and round-trips; a task query returns known ids.
        index_dir = self.store.index_dir(Layer.LANGUAGE, "java")
        self.assertTrue(VectorIndex.exists(index_dir))
        loaded = VectorIndex.load(index_dir)
        self.assertEqual(len(loaded), result.index_size)

        query = self.embedder.embed(["add two integers together"])[0]
        hits = loaded.search(query, k=3)
        self.assertTrue(hits)
        known_ids = {ex.id for ex in stored}
        self.assertTrue(all(h.id in known_ids for h in hits))

    def test_bootstrap_is_idempotent(self) -> None:
        first = bootstrap(
            self.store, str(self.repo), language="java", embedder=self.embedder
        )
        second = bootstrap(
            self.store, str(self.repo), language="java", embedder=self.embedder
        )
        # Content-derived ids mean a re-run adds nothing new.
        self.assertEqual(second.exemplars_added, 0)
        self.assertEqual(second.index_size, first.index_size)
        self.assertEqual(
            len(self.store.load_exemplars(Layer.LANGUAGE, "java")), first.index_size
        )

    def test_author_filter_narrows_files(self) -> None:
        # The fixtures were committed by "Dev <dev@example.com>"; an unknown
        # author touches nothing, so no exemplars are mined.
        result = bootstrap(
            self.store,
            str(self.repo),
            author="nobody@nowhere.invalid",
            language="java",
            embedder=self.embedder,
        )
        self.assertEqual(result.files_scanned, 0)
        self.assertEqual(result.exemplars_added, 0)
        self.assertEqual(result.index_size, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
