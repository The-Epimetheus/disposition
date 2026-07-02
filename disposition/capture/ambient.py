"""Ambient Capture: mine newly authored code between corrections.

Bootstrap is a one-time prior over a repo's history; Ambient Capture is the
ongoing trickle. Each run looks at the commits authored since the last run (a
per-repo watermark) and folds their Java into the Language profile as `ambient`
Exemplars, so the corpus keeps tracking how the developer actually writes as
they write it. The first run just sets the watermark: capture is forward-looking
by design (the developer opts in going forward, not retroactively).

Local and inspectable: the watermark lives under ~/.disposition/provenance and
captured exemplars carry provenance "ambient", so they are easy to review.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..gitutil import git_lines, git_out
from ..java import chunk_java_file
from ..models import Exemplar, Layer
from .pipeline import CapturePipeline


@dataclass
class AmbientResult:
    commits: int
    files: int
    exemplars_added: int
    watermark: str
    baseline: bool = False   # True when this run only set the starting point


def _state_path(store) -> Path:
    return store.root / "provenance" / "ambient.yaml"


def _load_watermarks(store) -> dict:
    path = _state_path(store)
    if not path.exists():
        return {}
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("watermarks", {})


def _save_watermarks(store, marks: dict) -> None:
    path = _state_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"watermarks": marks}, sort_keys=False))


def _is_sha(line: str) -> bool:
    return len(line) == 40 and all(c in "0123456789abcdef" for c in line)


def capture(
    store,
    repo: str,
    *,
    author: str | None = None,
    language: str = "java",
    embedder: object | None = None,
) -> AmbientResult:
    """Fold Java authored since the last run into the profile as ambient exemplars."""
    head = git_out(repo, ["rev-parse", "HEAD"]).strip()
    marks = _load_watermarks(store)
    last = marks.get(repo)

    # First run establishes the baseline; capture only what comes after.
    if not last:
        if head:
            marks[repo] = head
            _save_watermarks(store, marks)
        return AmbientResult(0, 0, 0, head, baseline=True)

    log_args = ["log", f"{last}..HEAD", "--name-only", "--pretty=format:%H"]
    if author:
        log_args.insert(2, f"--author={author}")

    commits: set[str] = set()
    files: set[str] = set()
    for line in git_lines(repo, log_args):
        if _is_sha(line):
            commits.add(line)
        elif line.endswith(".java"):
            files.add(line)

    new: list[Exemplar] = []
    for rel in sorted(files):
        path = Path(repo) / rel
        if not path.exists():
            continue
        for chunk in chunk_java_file(str(path)):
            new.append(
                Exemplar(
                    id=Exemplar.make_id(rel, chunk.start_line, chunk.code),
                    code=chunk.code,
                    language=language,
                    layer=Layer.LANGUAGE,
                    source=rel,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    provenance="ambient",
                )
            )

    counts = CapturePipeline(store, language, embedder=embedder).capture(exemplars=new)
    added = counts.exemplars_added
    marks[repo] = head
    _save_watermarks(store, marks)
    return AmbientResult(len(commits), len(files), added, head)
