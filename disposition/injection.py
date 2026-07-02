"""Forced Injection strategies for the Style envelope (ADR 0003 / Q19).

Injection decides *how much* of the Style Profile we put in front of the model
for a given task. Retrieval (retrieval.retrieve) answers the "task-relevant
top-k" question; Injection wraps it with three configurable policies:

  A (full):    every Confirmed Active-Style rule + every exemplar. Maximal and
               task-independent -- use when context budget is generous.
  B (dynamic): delegate wholesale to retrieval.retrieve -- task-relevant top-k.
               This is the v1 default (config.injection["strategy"] == "B").
  C (hybrid):  all Confirmed Active-Style rules, but only the top-k task-
               relevant exemplars. Full taste, scoped examples.

Any unknown strategy falls back to "B" so misconfiguration degrades gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .embeddings import Embedder
from .models import Exemplar, Rule, Status
from .retrieval import retrieve
from .store import Store


@dataclass
class Injection:
    """The injected Style envelope: rules + exemplars. Mirrors Retrieved."""

    rules: list[Rule]
    exemplars: list[Exemplar]


def _confirmed_active_rules(
    store: Store, language: str, repo: str | Path | None = None
) -> list[Rule]:
    """Every Confirmed rule in the merged Active Style (Provisional dropped)."""
    return [
        r for r in store.active_style(language, repo) if r.status is Status.CONFIRMED
    ]


def build_injection(
    store: Store,
    *,
    language: str = "java",
    task: str | None = None,
    strategy: str = "B",
    embedder: Embedder | None = None,
    k_rules: int | None = None,
    k_exemplars: int = 5,
    repo: str | Path | None = None,
) -> Injection:
    """Assemble the Style envelope under the chosen Forced Injection strategy.

    See the module docstring for the A/B/C policies. `task` steers the dynamic
    (B) and hybrid (C) exemplar retrieval; it is ignored by the full (A) policy.
    `repo` folds that repo's committed PROJECT house style into the Cascade.
    """
    strat = (strategy or "B").upper()

    if strat == "A":
        # Full: all Confirmed rules + every exemplar, task-independent.
        return Injection(
            rules=_confirmed_active_rules(store, language, repo),
            exemplars=store.all_exemplars(language),
        )

    if strat == "C":
        # Hybrid: all Confirmed rules, but only task-relevant exemplars.
        got = retrieve(
            store,
            task=task or "",
            language=language,
            k_rules=k_rules,
            k_exemplars=k_exemplars,
            embedder=embedder,
            repo=repo,
        )
        return Injection(
            rules=_confirmed_active_rules(store, language, repo),
            exemplars=got.exemplars,
        )

    # Dynamic (B) and the fallback for any unknown strategy.
    got = retrieve(
        store,
        task=task or "",
        language=language,
        k_rules=k_rules,
        k_exemplars=k_exemplars,
        embedder=embedder,
        repo=repo,
    )
    return Injection(rules=got.rules, exemplars=got.exemplars)
