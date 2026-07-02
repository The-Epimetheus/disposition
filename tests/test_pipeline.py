"""Tests for the Capture pipeline: the shared persist tail (Exemplars + Rules).

Exercises CapturePipeline against a temp-dir Store: adding Exemplars rebuilds the
derived index, dedup keeps counts honest, a rules-only call leaves the index
untouched, and an empty call is a clean no-op. Offline: LocalEmbedder only, no
network, no LLM. Runs standalone via `python3 tests/test_pipeline.py` and under
`python3 -m unittest discover`.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.capture.pipeline import CaptureCounts, CapturePipeline
from disposition.embeddings import LocalEmbedder
from disposition.index import VectorIndex
from disposition.models import Exemplar, Layer, Rule, Status
from disposition.store import Store


def _exemplar(code: str, source: str = "src.java") -> Exemplar:
    return Exemplar(
        id=Exemplar.make_id(source, 0, code),
        code=code,
        language="java",
        layer=Layer.LANGUAGE,
        source=source,
        provenance="test",
    )


def _rule(key: str, text: str) -> Rule:
    return Rule(
        key=key,
        text=text,
        status=Status.CONFIRMED,
        layer=Layer.LANGUAGE,
        confidence=0.9,
        provenance="test",
    )


class CapturePipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Store(pathlib.Path(tempfile.mkdtemp()))
        self.store.scaffold("java")
        self.embedder = LocalEmbedder(dim=64)
        self.pipeline = CapturePipeline(self.store, "java", embedder=self.embedder)

    def test_capture_exemplars_and_rules(self) -> None:
        ex = _exemplar("class A { void f() { return; } }")
        rule = _rule("control-flow", "Prefer early returns.")
        counts = self.pipeline.capture(exemplars=[ex], rules=[rule])

        self.assertIsInstance(counts, CaptureCounts)
        self.assertEqual(counts.exemplars_added, 1)
        self.assertEqual(counts.rules_added, 1)
        self.assertEqual(counts.index_size, 1)

        # Exemplar and Rule persisted to the LANGUAGE layer.
        stored = self.store.load_exemplars(Layer.LANGUAGE, "java")
        self.assertEqual([e.id for e in stored], [ex.id])
        rules = self.store.load_rules(Layer.LANGUAGE, "java")
        self.assertEqual([r.key for r in rules], ["control-flow"])

        # Index was rebuilt, round-trips, and holds the exemplar id.
        index_dir = self.store.index_dir(Layer.LANGUAGE, "java")
        self.assertTrue(VectorIndex.exists(index_dir))
        loaded = VectorIndex.load(index_dir)
        self.assertEqual(len(loaded), 1)
        hits = loaded.search(self.embedder.embed([ex.code])[0], k=3)
        self.assertIn(ex.id, {h.id for h in hits})

    def test_dedup_reports_zero_but_keeps_index_honest(self) -> None:
        ex = _exemplar("class B { int g() { return 1; } }")
        first = self.pipeline.capture(exemplars=[ex])
        self.assertEqual(first.exemplars_added, 1)
        self.assertEqual(first.index_size, 1)

        # Same content id: nothing new added, but the index still reflects the
        # single stored exemplar (rebuilt even on zero-added).
        second = self.pipeline.capture(exemplars=[ex])
        self.assertEqual(second.exemplars_added, 0)
        self.assertEqual(second.index_size, 1)
        self.assertEqual(len(self.store.load_exemplars(Layer.LANGUAGE, "java")), 1)

    def test_rules_only_leaves_index_untouched(self) -> None:
        index_dir = self.store.index_dir(Layer.LANGUAGE, "java")

        first = self.pipeline.capture(rules=[_rule("naming", "Use camelCase.")])
        self.assertEqual(first.exemplars_added, 0)
        self.assertEqual(first.rules_added, 1)
        self.assertEqual(first.index_size, 0)
        # Never built: no index files exist.
        self.assertFalse(VectorIndex.exists(index_dir))

        # Newest-wins by key: re-merging the same key updates rather than adds.
        second = self.pipeline.capture(rules=[_rule("naming", "Use snake_case.")])
        self.assertEqual(second.rules_added, 0)
        rules = self.store.load_rules(Layer.LANGUAGE, "java")
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].text, "Use snake_case.")

    def test_empty_capture_is_a_noop(self) -> None:
        counts = self.pipeline.capture()
        self.assertEqual(counts.exemplars_added, 0)
        self.assertEqual(counts.rules_added, 0)
        self.assertEqual(counts.index_size, 0)
        self.assertFalse(
            VectorIndex.exists(self.store.index_dir(Layer.LANGUAGE, "java"))
        )
        self.assertEqual(self.store.load_exemplars(Layer.LANGUAGE, "java"), [])
        self.assertEqual(self.store.load_rules(Layer.LANGUAGE, "java"), [])


if __name__ == "__main__":
    unittest.main()
