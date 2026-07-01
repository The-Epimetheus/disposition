"""A tiny in-memory vector index with cosine search and disk persistence.

This is the retrieval substrate for exemplars (ADR 0006). It is deliberately
brute-force: exemplar counts per profile are small, so a NumPy matmul over the
whole matrix beats the complexity of a real ANN library. Vectors are assumed
L2-normalized by the Embedder, so cosine similarity is a plain dot product; we
re-normalize defensively on `add` to keep search honest regardless of caller.

Persistence is two files in a directory: `vectors.npz` (the id-ordered matrix)
and `meta.json` (dim, ids, per-id metadata), so an index round-trips exactly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class IndexHit:
    """One search result: the exemplar id, its cosine score, and its metadata."""

    id: str
    score: float
    metadata: dict


class VectorIndex:
    """Brute-force cosine index over unit vectors of a fixed dimension."""

    def __init__(self, dim: int) -> None:
        self.dim = int(dim)
        self._ids: list[str] = []
        self._meta: dict[str, dict] = {}
        # Rows align with self._ids; empty (0, dim) matrix until first add.
        self._matrix: np.ndarray = np.zeros((0, self.dim), dtype=np.float32)

    def __len__(self) -> int:
        return len(self._ids)

    def _normalize(self, vector: np.ndarray) -> np.ndarray:
        """Coerce to (dim,) float32 and L2-normalize (zero stays zero)."""
        vec = np.asarray(vector, dtype=np.float32).reshape(-1)
        if vec.shape[0] != self.dim:
            raise ValueError(f"expected dim {self.dim}, got {vec.shape[0]}")
        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec = vec / norm
        return vec

    def add(self, id: str, vector: np.ndarray, metadata: dict) -> None:
        """Insert or overwrite the row for `id`."""
        vec = self._normalize(vector)
        if id in self._meta:
            row = self._ids.index(id)
            self._matrix[row] = vec
        else:
            self._ids.append(id)
            self._matrix = np.vstack([self._matrix, vec[None, :]])
        self._meta[id] = dict(metadata)

    def add_many(self, items: list[tuple[str, np.ndarray, dict]]) -> None:
        """Batch add; each item is (id, vector, metadata)."""
        for id, vector, metadata in items:
            self.add(id, vector, metadata)

    def search(self, vector: np.ndarray, k: int = 8) -> list[IndexHit]:
        """Return the top-k hits by cosine similarity, descending."""
        if len(self._ids) == 0 or k <= 0:
            return []
        query = self._normalize(vector)
        scores = self._matrix @ query  # unit rows * unit query = cosine
        k = min(k, len(self._ids))
        # argpartition for the top-k, then sort that slice by score desc.
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [
            IndexHit(id=self._ids[i], score=float(scores[i]), metadata=self._meta[self._ids[i]])
            for i in top
        ]

    # --- persistence -----------------------------------------------------

    def save(self, directory: Path) -> None:
        """Write vectors.npz + meta.json into `directory` (created if absent)."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        np.savez(directory / "vectors.npz", matrix=self._matrix)
        meta = {"dim": self.dim, "ids": self._ids, "meta": self._meta}
        (directory / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    @classmethod
    def exists(cls, directory: Path) -> bool:
        """True if both persistence files are present in `directory`."""
        directory = Path(directory)
        return (directory / "vectors.npz").exists() and (directory / "meta.json").exists()

    @classmethod
    def load(cls, directory: Path) -> "VectorIndex":
        """Reconstruct an index previously written by `save`."""
        directory = Path(directory)
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        index = cls(int(meta["dim"]))
        index._ids = list(meta["ids"])
        index._meta = {k: dict(v) for k, v in meta["meta"].items()}
        with np.load(directory / "vectors.npz") as data:
            index._matrix = data["matrix"].astype(np.float32)
        return index
