"""Cold-start archetypes: starting priors for developers with little history.

Bootstrap mines Style from real code, but a new developer (or a fresh repo)
has little to mine. An archetype is a small, hand-picked bundle of seed Rules
that names a recognisable coding disposition, so onboarding yields a usable
profile on day one. Seeds land in the Language layer as PROVISIONAL with
provenance "archetype" (ADR 0008: nothing steers hard until it earns trust);
they are refined -- confirmed, edited, or overridden -- as real evidence
accrues through Bootstrap and Induction.
"""

from __future__ import annotations

from .models import Layer, Rule, Status
from .store import Store

# Each archetype is a list of seed Rules as plain dicts. `mechanical` marks a
# Rule that a formatter/linter could enforce, versus a judgement call; it is
# carried through as a tag so downstream triage can treat the two differently.
ARCHETYPES: dict[str, list[dict]] = {
    # Battle-tested Android style: fail fast, never trust input, log with a TAG.
    "android-defensive": [
        {"key": "guard-clauses",
         "text": "Open methods with guard clauses that return early on bad input.",
         "mechanical": False},
        {"key": "null-checks",
         "text": "Null-check arguments and callback results before dereferencing.",
         "mechanical": False},
        {"key": "logging",
         "text": "Log with a per-class TAG constant and android.util.Log, not System.out.",
         "mechanical": True},
        {"key": "error-handling",
         "text": "Catch narrowly and degrade gracefully rather than crashing the UI thread.",
         "mechanical": False},
    ],
    # A functional-core disposition: values over mutation, pipelines over loops.
    "functional-immutable": [
        {"key": "immutability",
         "text": "Prefer final fields and immutable value objects; avoid in-place mutation.",
         "mechanical": False},
        {"key": "streams",
         "text": "Express collection transforms as stream pipelines rather than manual loops.",
         "mechanical": False},
        {"key": "pure-functions",
         "text": "Keep methods pure where possible; isolate side effects at the edges.",
         "mechanical": False},
        {"key": "null-handling",
         "text": "Use Optional instead of returning null from public methods.",
         "mechanical": True},
    ],
    # Less is more: small units, few moving parts, standard library first.
    "minimalist": [
        {"key": "method-size",
         "text": "Keep methods short and single-purpose; extract once they grow past a screen.",
         "mechanical": False},
        {"key": "dependencies",
         "text": "Reach for the standard library before adding a third-party dependency.",
         "mechanical": False},
        {"key": "naming",
         "text": "Name things plainly; avoid abbreviations and clever indirection.",
         "mechanical": False},
    ],
}


def list_archetypes() -> list[str]:
    """The names of the available cold-start archetypes."""
    return list(ARCHETYPES)


def apply_archetype(store: Store, name: str, *, language: str = "java") -> int:
    """Seed an archetype's Rules into the Language layer, merged by key.

    Seeds are PROVISIONAL with provenance "archetype" so they inform but do not
    hard-steer generation until confirmed. Existing same-key Rules win (we do
    not clobber real, earned Style), so the return value is the number of *new*
    Rules actually added.
    """
    seeds = ARCHETYPES.get(name)
    if seeds is None:
        raise ValueError(
            f"unknown archetype {name!r}; choose one of {list_archetypes()}"
        )

    existing = store.load_rules(Layer.LANGUAGE, language)
    by_key = {rule.key: rule for rule in existing}

    added = 0
    for seed in seeds:
        if seed["key"] in by_key:
            continue  # do not overwrite Style the developer already has
        by_key[seed["key"]] = Rule(
            key=seed["key"],
            text=seed["text"],
            status=Status.PROVISIONAL,
            layer=Layer.LANGUAGE,
            provenance="archetype",
            tags=["mechanical"] if seed.get("mechanical") else [],
        )
        added += 1

    if added:
        store.save_rules(Layer.LANGUAGE, list(by_key.values()), language)
    return added
