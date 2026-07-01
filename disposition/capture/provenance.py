"""Passive correction capture: track AI-generated spans, diff later edits.

M1's `reinforce` needs the developer to hand it both the AI code and their edit.
That is friction. Here we record where AI-generated code *landed* (a file and a
line range, anchored to the git blob at record time), then later scan those
spans against the file's current contents. Any span that changed is a candidate
correction: we route it through the same behavior-preserving classifier as
`reinforce`, so a taste edit is learned and a bug fix is dropped, with no
explicit command per edit.

This is the LLM-classifier path from M1; the AST/test tiers arrive in M3.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..gitutil import git_out
from . import correction as correction_mod


@dataclass
class AISpan:
    """One recorded region of AI-generated code, anchored for later diffing."""

    id: str
    repo: str
    file: str                 # path relative to the repo root
    start_line: int
    end_line: int
    ai_code: str
    anchor: str = ""          # git blob sha of the file when recorded
    status: str = "open"      # open | resolved
    outcome: str = ""         # "" | correction | excluded | unchanged | missing


@dataclass
class ScanResult:
    scanned: int
    corrections: int
    excluded: int
    pending: int


def _spans_path(store) -> Path:
    return store.root / "provenance" / "spans.yaml"


def _load_spans(store) -> list[AISpan]:
    path = _spans_path(store)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [AISpan(**item) for item in data.get("spans", [])]


def _save_spans(store, spans: list[AISpan]) -> None:
    path = _spans_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"spans": [vars(s) for s in spans]}
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


def _blob_sha(repo: str, rel: str) -> str:
    """The git blob sha of a tracked file at HEAD, or "" if unavailable."""
    return git_out(repo, ["rev-parse", f"HEAD:{rel}"]).strip()


def _read_region(repo: str, rel: str, start_line: int, end_line: int) -> str | None:
    """Return the current text of a file's line range, or None if it is gone."""
    path = Path(repo) / rel
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(lines[start_line - 1 : end_line])


def record_span(
    store,
    repo: str,
    file: str,
    start_line: int,
    end_line: int,
    ai_code: str | None = None,
) -> AISpan:
    """Record that lines [start_line, end_line] of `file` are AI-generated.

    If `ai_code` is omitted we snapshot the file's current lines as the AI code,
    so the developer can run this right after a generation. The span is anchored
    to the file's git blob sha so a later scan can tell it apart from the edit.
    """
    if ai_code is None:
        ai_code = _read_region(repo, file, start_line, end_line) or ""
    span = AISpan(
        id=hashlib.sha1(
            f"{repo}:{file}:{start_line}:{ai_code}".encode("utf-8")
        ).hexdigest()[:16],
        repo=repo,
        file=file,
        start_line=start_line,
        end_line=end_line,
        ai_code=ai_code,
        anchor=_blob_sha(repo, file),
    )
    spans = [s for s in _load_spans(store) if s.id != span.id]
    spans.append(span)
    _save_spans(store, spans)
    return span


def scan(
    store,
    repo: str | None = None,
    *,
    language: str = "java",
    llm=None,
    embedder=None,
) -> ScanResult:
    """Diff every open span against its file and capture behavior-preserving edits.

    Unchanged spans stay open. A changed span is fed to `reinforce`, which
    classifies it: a preserving edit becomes a Correction (Exemplar + Rule) and
    the span resolves as `correction`; a behavior-changing edit resolves as
    `excluded`. A span whose file or region vanished resolves as `missing`.
    """
    spans = _load_spans(store)
    corrections = excluded = pending = 0

    for span in spans:
        if span.status != "open":
            continue
        if repo is not None and span.repo != repo:
            continue

        current = _read_region(span.repo, span.file, span.start_line, span.end_line)
        if current is None:
            span.status, span.outcome = "resolved", "missing"
            continue
        if current.strip() == span.ai_code.strip():
            pending += 1  # not edited yet
            continue

        result = correction_mod.reinforce(
            store,
            ai_code=span.ai_code,
            edited_code=current,
            language=language,
            llm=llm,
            embedder=embedder,
            source=f"{span.file}:{span.start_line}",
        )
        span.status = "resolved"
        if result.accepted:
            span.outcome = "correction"
            corrections += 1
        else:
            span.outcome = "excluded"
            excluded += 1

    _save_spans(store, spans)
    scanned = corrections + excluded
    return ScanResult(
        scanned=scanned, corrections=corrections, excluded=excluded, pending=pending
    )
