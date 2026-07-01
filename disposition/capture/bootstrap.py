"""Bootstrap a Language profile from an existing repository.

The cold-start path (ADR 0005): before any interview or correction, mine the
developer's real code as Exemplars. We list tracked *.java files via git,
optionally narrowing to what a given author has touched, chunk each file into
method/class units, and store those as LANGUAGE-layer Exemplars. Finally we
embed every Exemplar and persist a VectorIndex so retrieval works immediately.

Everything here is offline: git is a local subprocess and the embedder is the
deterministic LocalEmbedder. No network, no LLM.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..embeddings import Embedder, get_embedder
from ..index import VectorIndex
from ..java import chunk_java_file
from ..models import Exemplar, Layer


@dataclass
class BootstrapResult:
    """What a bootstrap run produced, for the caller/CLI to report."""

    exemplars_added: int
    files_scanned: int
    index_size: int


def _git_lines(repo_path: str, args: list[str]) -> list[str]:
    """Run a git command in `repo_path`, returning stripped non-empty lines.

    Returns [] on any failure (not a repo, git missing) so bootstrap degrades
    gracefully rather than raising on a malformed environment.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _tracked_java(repo_path: str, author: str | None) -> list[str]:
    """Relative paths of tracked *.java files, optionally scoped to `author`."""
    tracked = _git_lines(repo_path, ["ls-files", "*.java"])
    if not author:
        return tracked
    # Files this author authored/touched, intersected with tracked set so we
    # never chunk a path that has since been deleted.
    touched = set(
        _git_lines(
            repo_path,
            ["log", f"--author={author}", "--name-only", "--pretty=format:"],
        )
    )
    return [path for path in tracked if path in touched]


def bootstrap(
    store,
    repo_path: str,
    *,
    author: str | None = None,
    language: str = "java",
    embedder: Embedder | None = None,
    limit: int = 200,
) -> BootstrapResult:
    """Mine `repo_path` for Java exemplars and build the retrieval index.

    Lists tracked *.java (optionally narrowed to `author`), chunks each into
    method/class units, stores them as LANGUAGE-layer Exemplars (deduped by
    content id), then embeds every LANGUAGE exemplar into a saved VectorIndex.
    """
    embedder = embedder or get_embedder()
    files = _tracked_java(repo_path, author)[:limit]

    new: list[Exemplar] = []
    for rel in files:
        abs_path = str(Path(repo_path) / rel)
        for chunk in chunk_java_file(abs_path):
            new.append(
                Exemplar(
                    id=Exemplar.make_id(rel, chunk.start_line, chunk.code),
                    code=chunk.code,
                    language=language,
                    layer=Layer.LANGUAGE,
                    source=rel,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    provenance="bootstrap",
                )
            )

    exemplars_before = len(store.load_exemplars(Layer.LANGUAGE, language))
    merged = store.add_exemplars(Layer.LANGUAGE, new, language)
    added = len(merged) - exemplars_before

    # Rebuild the index over the full LANGUAGE exemplar set (the index is a
    # derived cache; a clean rebuild keeps ids and vectors in lockstep).
    index = VectorIndex(embedder.dim)
    if merged:
        vectors = embedder.embed([ex.code for ex in merged])
        index.add_many(
            [
                (ex.id, vectors[i], {"source": ex.source, "start_line": ex.start_line})
                for i, ex in enumerate(merged)
            ]
        )
    index.save(store.index_dir(Layer.LANGUAGE, language))

    return BootstrapResult(
        exemplars_added=added,
        files_scanned=len(files),
        index_size=len(index),
    )
