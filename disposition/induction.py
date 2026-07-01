"""Induce candidate Rules from the developer's Exemplars, then triage them.

Induction is the "distillation" step (see CONTEXT.md): an adversarial LLM pass
reads the accumulated Exemplars and proposes plain-language Rules that would
explain them. Each candidate is tagged `mechanical` when it is a purely
syntactic habit (formatting, casing, brace style) rather than a judgement call.

Triage then decides what actually enters the Style Profile. Mechanical,
high-confidence candidates are safe to auto-Confirm; anything requiring taste is
kept Provisional until a human blesses it. New Rules are merged into the
Language layer (ADR 0008: rules.yaml stays hand-editable).
"""

from __future__ import annotations

from dataclasses import dataclass

from .llm import get_llm
from .models import Layer, Rule, Status
from .store import Store

# A mechanical candidate needs this much confidence before it is auto-Confirmed;
# below it we stay conservative and leave it Provisional for review.
_AUTO_CONFIRM_MIN = 0.7


@dataclass
class Candidate:
    """A proposed Rule not yet admitted to the Profile."""

    key: str
    text: str
    confidence: float
    mechanical: bool


_INDUCE_SYSTEM = (
    "You distill a developer's coding taste into rules. You are adversarial: "
    "propose only rules the exemplars actually support, and mark as mechanical "
    "any rule that is purely syntactic (formatting, casing, brace placement, "
    "import ordering) rather than a design judgement."
)


def induce(
    store: Store,
    *,
    language: str = "java",
    llm=None,
) -> list[Candidate]:
    """Ask the LLM to propose candidate Rules over all exemplars for a language."""
    llm = llm or get_llm()
    exemplars = store.all_exemplars(language)
    if not exemplars:
        return []

    blocks = "\n\n".join(
        f"// exemplar {i} ({ex.provenance or 'unknown'})\n{ex.code}"
        for i, ex in enumerate(exemplars)
    )
    prompt = (
        f"Here are {len(exemplars)} {language} code exemplars written by one "
        "developer. Infer the style rules they imply. Return a JSON array of "
        'objects: {"key": short-slug, "text": one-sentence rule, '
        '"confidence": 0..1, "mechanical": true|false}.\n\n'
        f"{blocks}"
    )
    raw = llm.json(prompt, system=_INDUCE_SYSTEM)
    # Tolerate either a bare array or a wrapping object with a "candidates" key.
    items = raw.get("candidates", []) if isinstance(raw, dict) else raw

    candidates: list[Candidate] = []
    for item in items:
        if not isinstance(item, dict) or "key" not in item:
            continue
        candidates.append(
            Candidate(
                key=str(item["key"]),
                text=str(item.get("text", "")),
                confidence=float(item.get("confidence", 0.5)),
                mechanical=bool(item.get("mechanical", False)),
            )
        )
    return candidates


def _to_rule(cand: Candidate, status: Status) -> Rule:
    return Rule(
        key=cand.key,
        text=cand.text,
        status=status,
        layer=Layer.LANGUAGE,
        confidence=cand.confidence,
        provenance="induction",
        tags=["mechanical"] if cand.mechanical else [],
    )


def triage(
    store: Store,
    candidates: list[Candidate],
    *,
    language: str = "java",
    auto: bool = False,
    input_fn=input,
    output_fn=print,
) -> dict:
    """Sort candidates into Confirmed/Provisional and merge them into the Profile.

    Mechanical, high-confidence candidates are auto-Confirmed. In `auto` mode
    (the test/non-interactive path) every remaining candidate lands Provisional.
    Interactively, the human may confirm/edit/reject each non-mechanical one;
    anything left unreviewed defaults to Provisional (safe, non-steering).
    """
    accepted: list[Rule] = []
    confirmed = provisional = 0

    for cand in candidates:
        # Mechanical habits with strong support are safe to admit outright.
        if cand.mechanical and cand.confidence >= _AUTO_CONFIRM_MIN:
            accepted.append(_to_rule(cand, Status.CONFIRMED))
            confirmed += 1
            continue

        if auto:
            accepted.append(_to_rule(cand, Status.PROVISIONAL))
            provisional += 1
            continue

        status = _prompt_one(cand, input_fn=input_fn, output_fn=output_fn)
        if status is None:  # rejected
            continue
        accepted.append(_to_rule(cand, status))
        if status is Status.CONFIRMED:
            confirmed += 1
        else:
            provisional += 1

    _merge(store, accepted, language)
    return {"confirmed": confirmed, "provisional": provisional}


def _prompt_one(cand: Candidate, *, input_fn, output_fn) -> Status | None:
    """Interactively review one candidate. Returns a Status, or None to reject."""
    output_fn(f"\nCandidate [{cand.key}] (confidence {cand.confidence:.2f})")
    output_fn(f"  {cand.text}")
    choice = input_fn("[c]onfirm / [p]rovisional / [r]eject? ").strip().lower()
    if choice.startswith("c"):
        return Status.CONFIRMED
    if choice.startswith("r"):
        return None
    # Anything else (including empty) defaults to the safe, non-steering state.
    return Status.PROVISIONAL


def _merge(store: Store, new: list[Rule], language: str) -> None:
    """Merge new Rules into the Language layer, replacing same-key entries."""
    existing = store.load_rules(Layer.LANGUAGE, language)
    by_key = {rule.key: rule for rule in existing}
    for rule in new:
        by_key[rule.key] = rule
    store.save_rules(Layer.LANGUAGE, list(by_key.values()), language)
