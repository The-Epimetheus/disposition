"""The Verification Gate: an adversarial judge that guards the Style envelope.

Generation is only half the loop. The Gate re-reads the model's output and
hunts for places it steps outside the developer's Active Style, citing the Rule
or Exemplar it breaks (ADR 0006). The judge is deliberately adversarial: it is
asked to *find deviations*, never to bless the output, because "is this ok?"
invites a rubber stamp. When a `regenerate` callback is supplied we feed the
violations back and retry up to a cap; if it never comes clean we escalate to
the human rather than silently ship a violation.

This is the LLM-judge tier only. A cheaper deterministic tier (linters, AST
checks) lands in M3; here every verdict comes from the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .config import Config
from .llm import LLM, get_llm


@dataclass
class Violation:
    """One place the output leaves the envelope, with the citation that proves it."""

    cite: str          # the Rule key or Exemplar id the output violates
    detail: str        # what specifically deviates


@dataclass
class GateResult:
    """The outcome of verifying (and possibly regenerating) an output."""

    passed: bool
    violations: list[Violation] = field(default_factory=list)
    regens: int = 0
    escalated: bool = False
    final_output: str = ""


# The judge's marching orders. Framed as an adversary so it looks for breaks
# rather than reassuring us; it must cite what each deviation violates.
_JUDGE_SYSTEM = (
    "You are an adversarial code reviewer enforcing one developer's personal "
    "style envelope. You are given the developer's Rules and Exemplars, plus a "
    "candidate OUTPUT. Find every place the OUTPUT deviates from this "
    "developer's envelope. For each deviation, cite the specific Rule key or "
    "Exemplar id it violates. Do not judge whether the code is good in general "
    "and do not approve it; only report deviations. If there are none, return "
    "an empty list."
)


def _render_rules(retrieved) -> str:
    # Compact, legible listing so the judge can cite by key.
    lines = []
    for rule in getattr(retrieved, "rules", []) or []:
        lines.append(f"- [{rule.key}] ({rule.status.value}) {rule.text}")
    return "\n".join(lines) if lines else "(none)"


def _render_exemplars(retrieved) -> str:
    lines = []
    for ex in getattr(retrieved, "exemplars", []) or []:
        lines.append(f"- id={ex.id} ({ex.language}):\n{ex.code}")
    return "\n\n".join(lines) if lines else "(none)"


def judge(output: str, retrieved, llm: LLM, task: str = "") -> list[Violation]:
    """Ask the judge to name where `output` deviates from the envelope.

    Returns a list of `Violation`; empty means the output is inside the
    envelope. The judge is prompted to hunt for deviations, not to approve.
    """
    prompt = (
        f"TASK:\n{task or '(unspecified)'}\n\n"
        f"DEVELOPER RULES:\n{_render_rules(retrieved)}\n\n"
        f"DEVELOPER EXEMPLARS:\n{_render_exemplars(retrieved)}\n\n"
        f"OUTPUT UNDER REVIEW:\n{output}\n\n"
        'Return a JSON list of objects, each {"cite": <rule key or exemplar '
        'id>, "detail": <what deviates>}. Return [] if nothing deviates.'
    )
    data = llm.json(prompt, system=_JUDGE_SYSTEM)
    # Tolerate either a bare list or a wrapped {"violations": [...]} shape.
    if isinstance(data, dict):
        data = data.get("violations", [])
    violations: list[Violation] = []
    for item in data or []:
        if isinstance(item, dict):
            violations.append(
                Violation(
                    cite=str(item.get("cite", "")),
                    detail=str(item.get("detail", "")),
                )
            )
    return violations


def verify(
    output: str,
    retrieved,
    *,
    llm: LLM | None = None,
    task: str = "",
    max_regens: int = 3,
    regenerate: Callable[[str, list[Violation]], str] | None = None,
) -> GateResult:
    """Judge `output`, regenerate against violations up to `max_regens`, escalate.

    Loop: judge -> if clean, pass; else if a `regenerate` callback exists, feed
    it the previous output and the violations to get a fresh attempt, and judge
    again. Stop when clean or the cap is hit; hitting the cap sets `escalated`.
    """
    if llm is None:
        # The judge runs on the configured judge model, distinct from generation.
        cfg = Config.load()
        llm = get_llm(config=cfg, fake=None)
        # get_llm resolves the generation model by default; retarget the judge
        # model when we ended up with a real client.
        if isinstance(llm, LLM) and type(llm).__name__ == "LLM":
            llm.model = cfg.models["judge"]

    current = output
    violations = judge(current, retrieved, llm, task=task)
    regens = 0

    while violations and regenerate is not None and regens < max_regens:
        current = regenerate(current, violations)
        regens += 1
        violations = judge(current, retrieved, llm, task=task)

    passed = not violations
    return GateResult(
        passed=passed,
        violations=violations,
        regens=regens,
        escalated=not passed,
        final_output=current,
    )
