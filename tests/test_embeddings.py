"""Tests for the offline `LocalEmbedder`.

Pure stdlib + numpy: no network, no downloads. Runs via
`python3 tests/test_embeddings.py` or `unittest discover`.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np

from disposition.embeddings import Embedder, LocalEmbedder, get_embedder


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


class TestLocalEmbedder(unittest.TestCase):
    def setUp(self):
        self.emb = LocalEmbedder(dim=512)

    def test_shape(self):
        out = self.emb.embed(["hello world", "goodbye", "third string"])
        self.assertEqual(out.shape, (3, 512))
        self.assertEqual(out.dtype, np.float32)
        self.assertEqual(self.emb.dim, 512)

    def test_l2_normalized(self):
        out = self.emb.embed(["public void run()", "int x = 0;", "another line"])
        norms = np.linalg.norm(out, axis=1)
        for n in norms:
            self.assertAlmostEqual(float(n), 1.0, places=5)

    def test_deterministic(self):
        a = self.emb.embed(["same text here"])
        b = LocalEmbedder(dim=512).embed(["same text here"])
        self.assertTrue(np.allclose(a, b))

    def test_similar_more_similar_than_dissimilar(self):
        out = self.emb.embed(
            [
                "for (int i = 0; i < n; i++) sum += arr[i];",
                "for (int i = 0; i < n; i++) total += arr[i];",
                "public String greet() { return \"hi\"; }",
            ]
        )
        near = cosine(out[0], out[1])
        far = cosine(out[0], out[2])
        self.assertGreater(near, far)

    def test_empty_string_safe(self):
        out = self.emb.embed(["", "x"])
        self.assertEqual(out.shape, (2, 512))
        # Empty text yields a zero (un-normalizable) vector, not a crash.
        self.assertAlmostEqual(float(np.linalg.norm(out[0])), 0.0, places=6)
        self.assertAlmostEqual(float(np.linalg.norm(out[1])), 1.0, places=5)

    def test_get_embedder_default(self):
        e = get_embedder()
        self.assertIsInstance(e, Embedder)
        self.assertIsInstance(e, LocalEmbedder)


if __name__ == "__main__":
    unittest.main()
