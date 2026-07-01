"""Tests for the brute-force cosine VectorIndex (ADR 0006).

Uses only NumPy + stdlib and a temp dir for persistence, so it runs via
`python3 tests/test_index.py` and under unittest discover. No network.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.index import IndexHit, VectorIndex


def unit(vec: list[float]) -> np.ndarray:
    v = np.asarray(vec, dtype=np.float32)
    return v / np.linalg.norm(v)


class VectorIndexTest(unittest.TestCase):
    def _sample(self) -> VectorIndex:
        # 3-D basis-ish vectors; query below is closest to "x", then "xy".
        index = VectorIndex(3)
        index.add_many(
            [
                ("x", unit([1.0, 0.0, 0.0]), {"name": "x"}),
                ("xy", unit([1.0, 1.0, 0.0]), {"name": "xy"}),
                ("z", unit([0.0, 0.0, 1.0]), {"name": "z"}),
            ]
        )
        return index

    def test_len_and_add_many(self):
        index = self._sample()
        self.assertEqual(len(index), 3)

    def test_search_cosine_ordering(self):
        index = self._sample()
        hits = index.search(unit([1.0, 0.2, 0.0]), k=3)
        self.assertEqual([h.id for h in hits], ["x", "xy", "z"])
        # Scores must be descending and carry metadata through.
        self.assertTrue(hits[0].score >= hits[1].score >= hits[2].score)
        self.assertIsInstance(hits[0], IndexHit)
        self.assertEqual(hits[0].metadata["name"], "x")

    def test_search_respects_k(self):
        index = self._sample()
        self.assertEqual(len(index.search(unit([1.0, 0.0, 0.0]), k=2)), 2)
        self.assertEqual(index.search(unit([1.0, 0.0, 0.0]), k=0), [])

    def test_search_empty_index(self):
        self.assertEqual(VectorIndex(4).search(np.ones(4, dtype=np.float32)), [])

    def test_add_overwrites_same_id(self):
        index = VectorIndex(3)
        index.add("a", unit([1.0, 0.0, 0.0]), {"v": 1})
        index.add("a", unit([0.0, 1.0, 0.0]), {"v": 2})
        self.assertEqual(len(index), 1)
        hit = index.search(unit([0.0, 1.0, 0.0]), k=1)[0]
        self.assertEqual(hit.metadata["v"], 2)
        self.assertAlmostEqual(hit.score, 1.0, places=5)

    def test_save_load_round_trip(self):
        index = self._sample()
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp) / "idx"
            self.assertFalse(VectorIndex.exists(directory))
            index.save(directory)
            self.assertTrue(VectorIndex.exists(directory))

            loaded = VectorIndex.load(directory)
            self.assertEqual(len(loaded), len(index))
            self.assertEqual(loaded.dim, index.dim)

            query = unit([1.0, 0.2, 0.0])
            before = index.search(query, k=3)
            after = loaded.search(query, k=3)
            self.assertEqual([h.id for h in before], [h.id for h in after])
            for b, a in zip(before, after):
                self.assertAlmostEqual(b.score, a.score, places=6)
                self.assertEqual(b.metadata, a.metadata)


if __name__ == "__main__":
    unittest.main(verbosity=2)
