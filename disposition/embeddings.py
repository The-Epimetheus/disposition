"""Offline, deterministic text embeddings.

Retrieval (ADR 0007) needs vectors for code exemplars and tasks, but M1 must
run with no network and no model downloads. `LocalEmbedder` hashes character
n-grams into a fixed-width vector with a stable hash, so the same text always
maps to the same L2-normalized point. It is crude but reproducible and offline.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

import numpy as np


class Embedder(ABC):
    """Maps texts to unit vectors in a fixed-dimension space."""

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """Return shape (n, dim), float32, each row L2-normalized."""

    @property
    @abstractmethod
    def dim(self) -> int:
        """Dimensionality of the output vectors."""


# Character n-gram sizes hashed into the vector. Small n captures spelling and
# token shape (casing, punctuation) without any learned vocabulary.
_NGRAMS = (3, 4, 5)


class LocalEmbedder(Embedder):
    """Deterministic hashing embedder: char n-grams -> fixed dim, L2-normalized.

    No downloads, no `sentence-transformers`; just `hashlib`. Buckets each
    n-gram of the input onto a dimension (with a sign bit so collisions can
    cancel rather than only accumulate), then normalizes. Similar strings share
    many n-grams and so land near each other on the unit sphere.
    """

    def __init__(self, dim: int = 512) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _vector(self, text: str) -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)
        # Pad short strings so even 1-2 char inputs yield some n-grams.
        s = text.lower()
        if not s:
            return vec
        for n in _NGRAMS:
            padded = s if len(s) >= n else s.ljust(n)
            for i in range(len(padded) - n + 1):
                gram = padded[i : i + n]
                # Stable 8-byte digest -> bucket index + sign, both reproducible.
                h = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
                val = int.from_bytes(h, "big")
                bucket = val % self._dim
                sign = 1.0 if (val >> 63) & 1 else -1.0
                vec[bucket] += sign
        return vec

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self._dim), dtype=np.float32)
        for row, text in enumerate(texts):
            vec = self._vector(text)
            norm = float(np.linalg.norm(vec))
            if norm > 0.0:
                vec = vec / norm
            out[row] = vec
        return out


def get_embedder(config=None) -> Embedder:
    """Default embedder for the pipeline. Offline `LocalEmbedder` for M1."""
    return LocalEmbedder()
