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

from dataclasses import dataclass
from pathlib import Path

from ..embeddings import Embedder
from ..gitutil import git_lines
from ..java import chunk_java_file
from ..models import Exemplar, Layer


@dataclass
class BootstrapResult:
    """What a bootstrap run produced, for the caller/CLI to report."""

    exemplars_added: int
    files_scanned: int
    index_size: int


def _tracked_java(repo_path: str, author: str | None) -> list[str]:
    """Relative paths of tracked *.java files, optionally scoped to `author`."""
    tracked = git_lines(repo_path, ["ls-files", "*.java"])
    if not author:
        return tracked
    # Files this author authored/touched, intersected with tracked set so we
    # never chunk a path that has since been deleted.
    touched = set(
        git_lines(
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
    index_size = store.rebuild_index(Layer.LANGUAGE, language, embedder=embedder)

    return BootstrapResult(
        exemplars_added=added,
        files_scanned=len(files),
        index_size=index_size,
    )
