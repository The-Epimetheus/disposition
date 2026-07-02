"""Assemble the Style envelope for a task: rules + retrieved exemplars.

Retrieval (ADR 0006/0007) is the read side of a Style Profile. Given a task
description we return (a) the merged Active Style rules, capped by confidence,
and (b) the handful of the developer's own exemplars nearest the task in the
embedding space. The exemplar index is a derived cache: we load it from disk
when present, otherwise rebuild it on the fly from stored exemplars so retrieval
never depends on a prior indexing pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .embeddings import Embedder, get_embedder
from .index import VectorIndex
from .models import Exemplar, Layer, Rule, Status
from .store import Store


@dataclass
class Retrieved:
    """The Style envelope handed to generation/judging: rules and exemplars."""

    rules: list[Rule]
    exemplars: list[Exemplar]


def _load_index(store: Store, language: str, embedder: Embedder) -> tuple[VectorIndex, dict[str, Exemplar]]:
    """Load the LANGUAGE exemplar index, or build one from stored exemplars.

    Returns the index plus an id->Exemplar map so search hits map back to the
    full records (the index only stores vectors + light metadata).
    """
    exemplars = store.all_exemplars(language)
    by_id = {ex.id: ex for ex in exemplars}
    directory = store.index_dir(Layer.LANGUAGE, language)
    if VectorIndex.exists(directory):
        cached = VectorIndex.load(directory)
        # The index is a derived cache keyed to one embedder. If its dim no
        # longer matches the active embedder, the developer switched embedders
        # in config, so the cache is stale; fall through and rebuild transiently.
        if cached.dim == embedder.dim:
            return cached, by_id
    # No cached index: build a transient one over whatever exemplars we have.
    index = VectorIndex(embedder.dim)
    if exemplars:
        vectors = embedder.embed([ex.code for ex in exemplars])
        index.add_many(
            [(ex.id, vectors[i], {"source": ex.source}) for i, ex in enumerate(exemplars)]
        )
    return index, by_id


def _cap_rules(rules: list[Rule], k_rules: int) -> list[Rule]:
    """Keep every Confirmed rule; fill the remaining budget with Provisional.

    Confirmed rules are the developer's committed taste and always ship. If the
    budget still has room, the highest-confidence Provisional rules follow. This
    keeps the injected envelope small without dropping anything confirmed.
    """
    confirmed = [r for r in rules if r.status is Status.CONFIRMED]
    provisional = sorted(
        (r for r in rules if r.status is Status.PROVISIONAL),
        key=lambda r: r.confidence,
        reverse=True,
    )
    room = max(0, k_rules - len(confirmed))
    return confirmed + provisional[:room]


def retrieve(
    store: Store,
    *,
    task: str,
    language: str = "java",
    k_rules: int | None = None,
    k_exemplars: int = 5,
    embedder: Embedder | None = None,
    repo: str | Path | None = None,
) -> Retrieved:
    """Build the Style envelope for `task` in `language`.

    Rules come from the already-merged Active Style (Cascade has resolved
    conflicts); pass `repo` to fold that repo's committed PROJECT house style
    into the merge. The rule budget `k_rules` defaults to the configured
    budgets.retrieval_top_k. Exemplars come from a nearest-neighbour search
    over the task text. Exemplars that plainly contradict an applicable
    Confirmed rule are dropped (ADR 0010); for M1 this is a lightweight keyword
    check and is a no-op when there is no clear signal.
    """
    embedder = embedder or get_embedder()
    if k_rules is None:
        k_rules = int(Config.load().budgets.get("retrieval_top_k", 12))

    rules = _cap_rules(store.active_style(language, repo), k_rules)

    index, by_id = _load_index(store, language, embedder)
    query = embedder.embed([task])[0]
    hits = index.search(query, k=max(k_exemplars, 0))

    exemplars: list[Exemplar] = []
    for hit in hits:
        ex = by_id.get(hit.id)
        if ex is None:
            continue  # index outran the exemplar store; skip stale ids
        if _violates_confirmed(ex, rules):
            continue
        exemplars.append(ex)

    return Retrieved(rules=rules, exemplars=exemplars)


def _violates_confirmed(exemplar: Exemplar, rules: list[Rule]) -> bool:
    """Lightweight guard: drop an exemplar that a Confirmed rule forbids.

    A real check (M3) would parse the code; for M1 we honour explicit negative
    directives only. When a Confirmed rule says to avoid/never/forbid some token
    and the exemplar's code contains that token, we treat it as a violation.
    Absent any such signal this returns False, so retrieval degrades gracefully.
    """
    code = exemplar.code.lower()
    negatives = ("avoid ", "never ", "no ", "don't ", "do not ", "forbid")
    for rule in rules:
        if rule.status is not Status.CONFIRMED:
            continue
        text = rule.text.lower()
        if not any(neg in text for neg in negatives):
            continue
        # Pull the word right after the negative cue and look for it in the code.
        for neg in negatives:
            idx = text.find(neg)
            if idx < 0:
                continue
            after = text[idx + len(neg):].strip().split()
            if after:
                token = after[0].strip(".,;:'\"()").lower()
                if len(token) >= 3 and token in code:
                    return True
    return False
