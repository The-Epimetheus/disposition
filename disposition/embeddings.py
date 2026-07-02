"""Text embeddings for retrieval, with two adapters behind one config seam.

Retrieval (ADR 0007) needs vectors for code exemplars and tasks. There are two
ways to get them here:

- `LocalEmbedder` (the default) hashes character n-grams into a fixed-width
  vector with a stable hash, so the same text always maps to the same
  L2-normalized point. It is crude but reproducible and needs no network or
  downloads, which is what M1 wanted.
- `SemanticEmbedder` runs a real code-aware embedding model via fastembed
  (ONNX, no torch). The model downloads once and then runs fully offline, so it
  stays inside the fully-local principle (ADR 0004) while giving much better
  neighbours than the hash. It is opt-in via the `semantic` extra.

`get_embedder(config)` picks between them from `models.embedding` in config.
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


class SemanticEmbedder(Embedder):
    """Real code-aware embeddings via fastembed (ONNX runtime, no torch).

    Wraps a fastembed `TextEmbedding` model. The model downloads once on first
    use and then runs offline, so it fits the fully-local principle (ADR 0004).
    `backend` lets tests inject any object with the fastembed interface (an
    `.embed(texts)` that yields one numpy vector per text); when None we import
    fastembed lazily so importing this module never requires the extra.

    The output dimension is read off the model itself (by embedding a probe
    string once) rather than hard-coded, so swapping in a different fastembed
    model just works.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", *, backend=None) -> None:
        self._model_name = model_name
        if backend is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # extra not installed
                raise ImportError(
                    "SemanticEmbedder needs fastembed; install it with "
                    'pip install "disposition[semantic]"'
                ) from exc
            backend = TextEmbedding(model_name=model_name)
        self._backend = backend
        self._dim: int | None = None  # filled lazily by the first probe

    @property
    def dim(self) -> int:
        # Ask the model its own width by embedding a probe once, then cache it.
        if self._dim is None:
            probe = next(iter(self._backend.embed(["probe"])))
            self._dim = int(np.asarray(probe).reshape(-1).shape[0])
        return self._dim

    def embed(self, texts: list[str]) -> np.ndarray:
        dim = self.dim
        out = np.zeros((len(texts), dim), dtype=np.float32)
        # fastembed returns an iterable of numpy vectors, one per input text.
        for row, vector in enumerate(self._backend.embed(texts)):
            vec = np.asarray(vector, dtype=np.float32).reshape(-1)
            norm = float(np.linalg.norm(vec))
            if norm > 0.0:
                vec = vec / norm
            out[row] = vec
        return out


def get_embedder(config=None) -> Embedder:
    """Resolve the embedder named by config (models.embedding).

    "local" (the default) is the offline hashing embedder; "semantic" is the
    real fastembed model. Anything else is a configuration mistake and we say
    so instead of silently ignoring it.
    """
    from .config import Config

    cfg = config or Config.load()
    name = str(cfg.models.get("embedding", "local"))
    if name == "local":
        return LocalEmbedder()
    if name == "semantic":
        return SemanticEmbedder()
    raise ValueError(
        f"unknown embedding model {name!r} in config.toml; "
        "valid options are 'local' and 'semantic'"
    )
