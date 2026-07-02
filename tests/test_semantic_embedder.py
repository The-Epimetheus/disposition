"""Tests for the fastembed-backed `SemanticEmbedder` and the config seam.

No network and no fastembed install required: we inject a fake backend that
mimics the fastembed `TextEmbedding` interface (an `.embed(texts)` that yields
one numpy vector per text). Runs via `python3 tests/test_semantic_embedder.py`
or `unittest discover`.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np

from disposition.embeddings import Embedder, SemanticEmbedder, get_embedder
from disposition.index import VectorIndex
from disposition.models import Exemplar, Layer
from disposition.retrieval import Retrieved, retrieve
from disposition.store import Store


class FakeBackend:
    """Stand-in for fastembed's TextEmbedding: .embed yields numpy vectors.

    Each text maps to a deterministic (unnormalized) vector of a fixed width so
    tests can check shape, dtype, normalization, and dim inference.
    """

    def __init__(self, width: int = 6) -> None:
        self.width = width

    def embed(self, texts):
        for i, _text in enumerate(texts):
            # Non-unit, non-zero vectors so the normalization step is exercised.
            yield np.arange(1 + i, 1 + i + self.width, dtype=np.float64)


class FakeConfig:
    """Minimal stand-in for Config: only the `models` mapping is read here."""

    def __init__(self, embedding: str) -> None:
        self.models = {"embedding": embedding}


class TestSemanticEmbedder(unittest.TestCase):
    def test_shape_and_dtype(self):
        emb = SemanticEmbedder(backend=FakeBackend(width=6))
        out = emb.embed(["one", "two", "three"])
        self.assertEqual(out.shape, (3, 6))
        self.assertEqual(out.dtype, np.float32)

    def test_rows_l2_normalized(self):
        emb = SemanticEmbedder(backend=FakeBackend(width=8))
        out = emb.embed(["alpha", "beta"])
        for n in np.linalg.norm(out, axis=1):
            self.assertAlmostEqual(float(n), 1.0, places=5)

    def test_dim_inferred_from_backend(self):
        emb = SemanticEmbedder(backend=FakeBackend(width=11))
        self.assertEqual(emb.dim, 11)
        # A different backend width yields a different inferred dim.
        self.assertEqual(SemanticEmbedder(backend=FakeBackend(width=3)).dim, 3)

    def test_is_an_embedder(self):
        self.assertIsInstance(SemanticEmbedder(backend=FakeBackend()), Embedder)


class TestGetEmbedder(unittest.TestCase):
    def test_unknown_name_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            get_embedder(FakeConfig("definitely-not-a-model"))
        # The error names the valid options.
        self.assertIn("local", str(ctx.exception))
        self.assertIn("semantic", str(ctx.exception))

    def test_semantic_missing_fastembed_raises_install_hint(self):
        # Simulate fastembed being absent: importing it raises ImportError.
        with mock.patch.dict(sys.modules, {"fastembed": None}):
            with self.assertRaises(ImportError) as ctx:
                get_embedder(FakeConfig("semantic"))
        self.assertIn("disposition[semantic]", str(ctx.exception))

    def test_semantic_returns_semantic_embedder_if_available(self):
        # If fastembed is importable, the "semantic" branch builds a
        # SemanticEmbedder; otherwise it raises the helpful install error.
        try:
            import fastembed  # noqa: F401

            available = True
        except ImportError:
            available = False

        if available:
            emb = get_embedder(FakeConfig("semantic"))
            self.assertIsInstance(emb, SemanticEmbedder)
        else:
            with self.assertRaises(ImportError) as ctx:
                get_embedder(FakeConfig("semantic"))
            self.assertIn("disposition[semantic]", str(ctx.exception))


class TestRetrievalDimGuard(unittest.TestCase):
    """A persisted index built at one dim must not be served to an embedder of
    another dim; retrieval should rebuild transiently instead of crashing."""

    def _seed_store(self, tmp: str) -> Store:
        store = Store(pathlib.Path(tmp))
        store.scaffold("java")
        exemplars = [
            Exemplar(
                id=Exemplar.make_id("A.java", 1, "class A {}"),
                code="class A {}",
                language="java",
                layer=Layer.LANGUAGE,
                source="A.java",
                provenance="bootstrap",
            ),
            Exemplar(
                id=Exemplar.make_id("B.java", 1, "class B {}"),
                code="class B {}",
                language="java",
                layer=Layer.LANGUAGE,
                source="B.java",
                provenance="bootstrap",
            ),
        ]
        store.add_exemplars(Layer.LANGUAGE, exemplars, "java")
        # Persist an index at dim 6 (matching the fake backend below).
        emb6 = SemanticEmbedder(backend=FakeBackend(width=6))
        vectors = emb6.embed([ex.code for ex in exemplars])
        index = VectorIndex(emb6.dim)
        index.add_many(
            [(ex.id, vectors[i], {"source": ex.source}) for i, ex in enumerate(exemplars)]
        )
        index.save(store.index_dir(Layer.LANGUAGE, "java"))
        return store

    def test_dim_mismatch_rebuilds_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._seed_store(tmp)
            # Retrieve with a DIFFERENT dim (10 vs the persisted 6). Passing
            # k_rules avoids reading config for the rule budget.
            embedder = SemanticEmbedder(backend=FakeBackend(width=10))
            got = retrieve(
                store,
                task="anything",
                language="java",
                k_rules=12,
                embedder=embedder,
            )
            self.assertIsInstance(got, Retrieved)
            # It did not crash; the transient rebuild returned exemplars.
            self.assertTrue(got.exemplars)


if __name__ == "__main__":
    unittest.main(verbosity=2)
