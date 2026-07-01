"""Reinforcement from in-editor corrections (ADR 0009).

When a developer edits AI-generated code, the diff is a signal about Style, but
only if the edit is *behavior-preserving*: a refactor that expresses taste, not
a bug fix that changes what the code does. We default to exclusion. A strict,
adversarial classifier gates every correction: unless the LLM is confident the
edit preserves behavior, we drop it, so bug fixes never masquerade as taste.

An accepted correction yields two artifacts: the edited code becomes a
`correction` Exemplar (the tacit texture), and the taste delta the LLM names
becomes a Provisional Rule on the Language layer (the legible statement).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..embeddings import get_embedder
from ..index import VectorIndex
from ..llm import get_llm
from ..models import Exemplar, Layer, Rule, Status

# Below this the edit is treated as behavior-changing and excluded (ADR 0009).
_PRESERVING_THRESHOLD = 0.7


@dataclass
class CorrectionResult:
    accepted: bool
    reason: str
    rule_added: bool
    exemplar_added: bool


def classify_behavior_preserving(
    ai_code: str, edited_code: str, llm
) -> tuple[bool, float, str]:
    """Adversarially decide whether the edit only changes taste, not behavior.

    The prompt asks the model to hunt for behavioral divergence rather than to
    bless the edit. We then apply a strict floor: preserving only when the model
    both says so and clears `_PRESERVING_THRESHOLD`; anything less is excluded.
    """
    prompt = (
        "You are auditing a developer's edit of AI-generated code. Your job is "
        "to find any way the EDIT changes observable behavior (outputs, side "
        "effects, control flow, exceptions, concurrency) versus the ORIGINAL. "
        "If it only reshapes style, naming, or structure while doing the same "
        "thing, it is behavior-preserving.\n\n"
        f"ORIGINAL:\n```\n{ai_code}\n```\n\n"
        f"EDIT:\n```\n{edited_code}\n```\n\n"
        'Return JSON: {"preserving": bool, "confidence": number 0..1, '
        '"reason": short string}. Confidence is how sure you are of the '
        "preserving verdict."
    )
    data = llm.json(prompt)
    if not isinstance(data, dict):
        return False, 0.0, "classifier returned no verdict"
    claimed = bool(data.get("preserving", False))
    confidence = float(data.get("confidence", 0.0))
    reason = str(data.get("reason", ""))
    # Strict default-exclude: both the verdict and the confidence must hold.
    preserving = claimed and confidence >= _PRESERVING_THRESHOLD
    return preserving, confidence, reason


def _taste_delta_rule(ai_code: str, edited_code: str, confidence: float, llm) -> Rule:
    """Ask the LLM to name the one preference the edit reveals, as a Rule."""
    prompt = (
        "A developer edited AI-generated code without changing its behavior. "
        "Name the single style preference the change reveals, as a reusable "
        "rule.\n\n"
        f"BEFORE:\n```\n{ai_code}\n```\n\n"
        f"AFTER:\n```\n{edited_code}\n```\n\n"
        'Return JSON: {"key": short-kebab-case-topic, "text": one imperative '
        "sentence stating the preference}."
    )
    data = llm.json(prompt)
    if not isinstance(data, dict):
        data = {}
    key = str(data.get("key") or "correction-delta").strip() or "correction-delta"
    text = str(data.get("text") or "").strip() or "Prefer the corrected form."
    return Rule(
        key=key,
        text=text,
        status=Status.PROVISIONAL,
        layer=Layer.LANGUAGE,
        confidence=confidence,
        provenance="correction",
    )


def reinforce(
    store,
    *,
    ai_code: str,
    edited_code: str,
    language: str = "java",
    llm=None,
    embedder=None,
    source: str = "",
) -> CorrectionResult:
    """Turn one AI-vs-edited diff into an Exemplar + Provisional Rule, if kept.

    Behavior-changing edits are rejected outright (default-exclude). A preserving
    edit persists the edited code as a `correction` Exemplar and the LLM-named
    taste delta as a Provisional Language-layer Rule, keeping any live vector
    index warm so the new Exemplar is retrievable immediately.
    """
    llm = llm or get_llm()
    preserving, confidence, reason = classify_behavior_preserving(
        ai_code, edited_code, llm
    )
    if not preserving:
        # Excluded: the edit likely fixes a bug, which is not a Style signal.
        return CorrectionResult(
            accepted=False, reason=reason, rule_added=False, exemplar_added=False
        )

    src = source or "correction"
    exemplar = Exemplar(
        id=Exemplar.make_id(src, 0, edited_code),
        code=edited_code,
        language=language,
        layer=Layer.LANGUAGE,
        source=src,
        provenance="correction",
    )
    store.add_exemplars(Layer.LANGUAGE, [exemplar], language)

    # Merge the taste-delta Rule into the Language layer, newest wins by key.
    rule = _taste_delta_rule(ai_code, edited_code, confidence, llm)
    existing = store.load_rules(Layer.LANGUAGE, language)
    by_key = {r.key: r for r in existing}
    by_key[rule.key] = rule
    store.save_rules(Layer.LANGUAGE, list(by_key.values()), language)

    # Keep a persisted index (if one exists) in step with the new Exemplar.
    embedder = embedder or get_embedder()
    index_dir = store.index_dir(Layer.LANGUAGE, language)
    if VectorIndex.exists(index_dir):
        index = VectorIndex.load(index_dir)
        if index.dim == embedder.dim:
            vector = embedder.embed([exemplar.code])[0]
            index.add(exemplar.id, vector, {"id": exemplar.id, "source": src})
            index.save(index_dir)

    return CorrectionResult(
        accepted=True, reason=reason, rule_added=True, exemplar_added=True
    )
