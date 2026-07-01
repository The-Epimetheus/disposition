"""Self-aging profile and Drift delta-queries (ADR 0009, ADR 0010).

Style is not a snapshot; it decays and it drifts. Two distinct mechanisms keep
a profile honest over time, and they are deliberately asymmetric in how much
authority they claim:

- `age_profile` is the quiet janitor. It leans on *time alone*: a Provisional
  Rule that was never reconfirmed loses confidence on a half-life curve, and
  once it falls below a floor it is dropped. Provisional Rules are guesses, so
  letting stale guesses fade is safe and needs no human in the loop. Confirmed
  Rules are the developer's explicit word and are NEVER silently touched here.

- `detect_drift` is the observer. When *recent evidence* (fresh corrections and
  ambient snippets) sustainedly contradicts a Confirmed Rule, we do not overrule
  the human -- we surface a Delta Query: a legible question that asks them to
  reconcile the rule with what their code now does (ADR 0010). Confirmed Rules
  only change by the developer answering that question.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from .llm import LLM, get_llm
from .models import Layer, Rule, Status
from .store import Store

# Provisional Rules below this decayed confidence are no longer worth steering
# generation and are dropped. Above it they linger, quietly weaker.
_DROP_FLOOR = 0.15


@dataclass
class DeltaQuery:
    """A surfaced contradiction between a Confirmed Rule and recent evidence.

    This is a question for the human, not a mutation: it names the rule, quotes
    the evidence that seems to contradict it, and asks how to reconcile them.
    """

    rule_key: str
    rule_text: str
    evidence: str
    question: str


def _as_date(value) -> datetime.date | None:
    """Coerce an ISO string or a date into a date; None when unparseable/empty."""
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _resolve_now(now) -> datetime.date:
    """The 'today' the aging math runs against; injectable for deterministic tests."""
    return _as_date(now) or datetime.date.today()


def age_profile(
    store: Store,
    *,
    language: str = "java",
    now=None,
    half_life_days: int = 90,
) -> dict:
    """Decay Provisional Rules by age and drop the ones that fade past the floor.

    Each Provisional Rule's confidence is multiplied by 0.5 ** (age/half_life),
    where age is days since `Rule.created`. Rules whose decayed confidence falls
    below `_DROP_FLOOR` are removed. Confirmed Rules are left exactly as-is --
    they only change through a Delta Query (see `detect_drift`). The updated
    layers are persisted via `store.save_rules`. Returns counts of aged/dropped.
    """
    today = _resolve_now(now)
    aged = 0
    dropped = 0

    # Age every layer the profile actually merges from (Personal + Language).
    layers = ((Layer.PERSONAL, None), (Layer.LANGUAGE, language))
    for layer, lang in layers:
        rules = store.load_rules(layer, lang)
        if not rules:
            continue
        kept: list[Rule] = []
        changed = False
        for rule in rules:
            # Confirmed Rules are the developer's word; never silently touched.
            if rule.status is Status.CONFIRMED:
                kept.append(rule)
                continue
            created = _as_date(rule.created)
            if created is None:
                # No birth date to age against -- leave the guess untouched.
                kept.append(rule)
                continue
            age_days = max(0, (today - created).days)
            decayed = rule.confidence * (0.5 ** (age_days / half_life_days))
            if decayed < _DROP_FLOOR:
                dropped += 1
                changed = True
                continue
            if decayed != rule.confidence:
                rule.confidence = decayed
                aged += 1
                changed = True
            kept.append(rule)
        if changed:
            store.save_rules(layer, kept, lang)

    return {"aged": aged, "dropped": dropped}


# The observer's brief: it is looking for *sustained* contradiction, not a
# one-off, and it must never invent a rule -- only cite the Confirmed ones given.
_DRIFT_SYSTEM = (
    "You watch one developer's recent code for signs that their settled style "
    "has drifted. You are given their CONFIRMED style Rules and a set of RECENT "
    "code snippets drawn from real corrections and ambient edits. Report only "
    "Confirmed Rules that the recent snippets *sustainedly* contradict -- a "
    "consistent, repeated pattern, not a single exception. Never invent a rule; "
    "only reference the keys you are given. If nothing drifts, return an empty "
    "list."
)


def _render_confirmed(rules: list[Rule]) -> str:
    lines = [f"- [{r.key}] {r.text}" for r in rules]
    return "\n".join(lines) if lines else "(none)"


def _render_recent(exemplars) -> str:
    lines = [
        f"- ({ex.provenance}, {ex.created}):\n{ex.code}" for ex in exemplars
    ]
    return "\n\n".join(lines) if lines else "(none)"


def detect_drift(
    store: Store,
    *,
    language: str = "java",
    llm: LLM | None = None,
    now=None,
    recent_days: int = 60,
) -> list[DeltaQuery]:
    """Surface Delta Queries where recent evidence contradicts a Confirmed Rule.

    Gathers recent Exemplars (provenance in {"correction", "ambient"} created
    within `recent_days`) and the Confirmed Rules, and asks the LLM whether the
    recent signal sustainedly contradicts any of them. Each reported
    contradiction becomes a `DeltaQuery` for the human to reconcile; nothing is
    mutated. Confirmed Rules only ever change by the developer answering these.
    """
    llm = llm or get_llm()
    today = _resolve_now(now)
    cutoff = today - datetime.timedelta(days=recent_days)

    confirmed = [
        r for r in store.active_style(language) if r.status is Status.CONFIRMED
    ]
    recent = []
    for ex in store.all_exemplars(language):
        if ex.provenance not in ("correction", "ambient"):
            continue
        created = _as_date(ex.created)
        if created is None or created < cutoff:
            continue
        recent.append(ex)

    # No settled rules or no fresh signal -> nothing could drift.
    if not confirmed or not recent:
        return []

    by_key = {r.key: r for r in confirmed}
    prompt = (
        f"CONFIRMED RULES:\n{_render_confirmed(confirmed)}\n\n"
        f"RECENT SNIPPETS:\n{_render_recent(recent)}\n\n"
        "Return a JSON list of objects, each "
        '{"rule_key": <one of the confirmed keys>, "evidence": <what in the '
        'snippets contradicts it>, "question": <the reconciling question to ask '
        'the developer>}. Return [] if nothing sustainedly drifts.'
    )
    data = llm.json(prompt, system=_DRIFT_SYSTEM)
    # Tolerate either a bare list or a wrapped {"contradictions": [...]} shape.
    if isinstance(data, dict):
        data = data.get("contradictions") or data.get("drift") or []

    queries: list[DeltaQuery] = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("rule_key", ""))
        rule = by_key.get(key)
        if rule is None:
            # The model must cite a real Confirmed Rule; ignore hallucinated keys.
            continue
        queries.append(
            DeltaQuery(
                rule_key=key,
                rule_text=rule.text,
                evidence=str(item.get("evidence", "")),
                question=str(
                    item.get("question")
                    or f"Recent code seems to contradict '{rule.text}'. Update it?"
                ),
            )
        )
    return queries
