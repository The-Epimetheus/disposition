"""The Verification Gate: an adversarial judge that guards the Style envelope.

Generation is only half the loop. The Gate re-reads the model's output and
hunts for places it steps outside the developer's Active Style, citing the Rule
or Exemplar it breaks (ADR 0006). The judge is deliberately adversarial: it is
asked to *find deviations*, never to bless the output, because "is this ok?"
invites a rubber stamp. When a `regenerate` callback is supplied we feed the
violations back and retry up to a cap; if it never comes clean we escalate to
the human rather than silently ship a violation.

Two tiers guard the envelope (ADR 0006). A cheap DETERMINISTIC tier runs first
each round -- pure string/pattern checks, no LLM -- and only what survives it
reaches the adversarial LLM judge above. The deterministic tier derives its
checks from the developer's own CONFIRMED *mechanical* Rules (plus a handful of
universal format checks), so it stays specific to this developer and averse to
false positives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .config import Config
from .llm import LLM, get_llm
from .models import Status


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


def _leading_ws(line: str) -> str:
    # The run of whitespace before the first non-space/tab character.
    return line[: len(line) - len(line.lstrip(" \t"))]


def deterministic_check(output: str, retrieved) -> list[Violation]:
    """The cheap tier: catch clear mechanical breaks with no LLM call.

    Runs before the judge. Emits `Violation`s for two sources:

    * A few *universal* format faults that are almost never intentional --
      trailing whitespace, and tab indentation where the output otherwise
      indents with spaces (mixed tabs). These cite a synthetic "format:" key.
    * The developer's own CONFIRMED Rules tagged "mechanical". We only act on
      rules whose text names a concretely checkable pattern (e.g. "System.out",
      "logging", "TAG" -> flag a literal ``System.out.println`` call). Rules
      that read as judgement (e.g. "final" for locals) are left to the judge.

    Deliberately conservative: each check is a definite, citable fault, so a
    clean output returns ``[]`` and never blocks generation on a guess.
    """
    violations: list[Violation] = []
    lines = output.splitlines()

    # --- Universal: trailing whitespace (ignore blank/whitespace-only lines). ---
    trailing = [
        i for i, line in enumerate(lines, 1)
        if line.strip() and line != line.rstrip()
    ]
    if trailing:
        where = ", ".join(str(n) for n in trailing[:5])
        more = "..." if len(trailing) > 5 else ""
        violations.append(
            Violation("format:trailing-whitespace", f"trailing whitespace on line(s) {where}{more}")
        )

    # --- Universal: tab indentation when spaces are the prevailing style. ---
    space_indented = any(_leading_ws(l).startswith(" ") for l in lines)
    tab_lines = [i for i, l in enumerate(lines, 1) if _leading_ws(l).startswith("\t")]
    if space_indented and tab_lines:
        where = ", ".join(str(n) for n in tab_lines[:5])
        more = "..." if len(tab_lines) > 5 else ""
        violations.append(
            Violation("format:mixed-tabs", f"tab indentation where spaces are used on line(s) {where}{more}")
        )

    # --- Rule-derived: only CONFIRMED, "mechanical"-tagged rules. ---
    for rule in getattr(retrieved, "rules", []) or []:
        if rule.status != Status.CONFIRMED or "mechanical" not in (rule.tags or []):
            continue
        text = rule.text.lower()
        # "final" for locals reads as judgement, not a mechanical pattern -> skip.
        if "final" in text:
            continue
        # A logging-discipline rule: flag the literal console print it forbids.
        if any(kw in text for kw in ("system.out", "logging", "tag")):
            if "System.out.println" in output:
                violations.append(
                    Violation(rule.key, "uses System.out.println; rule requires proper logging")
                )

    return violations


def llm_regenerator(
    llm: LLM, retrieved, task: str = ""
) -> Callable[[str, list[Violation]], str]:
    """A `regenerate` callback that re-asks `llm` to rewrite inside the envelope.

    Each retry is anchored to exactly what it broke: the previous attempt plus
    the judge's citations, alongside the same Rules and Exemplars, so the model
    fixes the violations instead of starting over.
    """

    def _regenerate(previous: str, violations: list[Violation]) -> str:
        cites = "\n".join(f"- [{v.cite}] {v.detail}" for v in violations)
        prompt = (
            f"TASK:\n{task or '(unspecified)'}\n\n"
            f"DEVELOPER RULES:\n{_render_rules(retrieved)}\n\n"
            f"DEVELOPER EXEMPLARS:\n{_render_exemplars(retrieved)}\n\n"
            f"PREVIOUS OUTPUT:\n{previous}\n\n"
            f"The previous output violated the developer's style:\n{cites}\n\n"
            "Rewrite the output so it honours every rule above and matches the "
            "exemplars' texture. Return only the rewritten code, no commentary."
        )
        return llm.complete(prompt)

    return _regenerate


def verify(
    output: str,
    retrieved,
    *,
    llm: LLM | None = None,
    task: str = "",
    max_regens: int | None = None,
    regenerate: Callable[[str, list[Violation]], str] | None = None,
) -> GateResult:
    """Check `output`, regenerate against violations up to `max_regens`, escalate.

    Each round runs the cheap deterministic tier FIRST, then the adversarial
    LLM judge, and combines their violations. Loop: check -> if clean, pass;
    else if a `regenerate` callback exists, feed it the previous output and the
    combined violations to get a fresh attempt, and check again. Stop when clean
    or the cap is hit; hitting the cap sets `escalated`. `max_regens` defaults
    to the configured budgets.max_regens (ADR 0006).
    """
    if max_regens is None:
        max_regens = int(Config.load().budgets.get("max_regens", 3))
    if llm is None:
        # The judge runs on the configured judge model, distinct from generation.
        cfg = Config.load()
        llm = get_llm(config=cfg, fake=None)
        # get_llm resolves the generation model by default; retarget the judge
        # model when we ended up with a real client.
        if isinstance(llm, LLM) and type(llm).__name__ == "LLM":
            llm.model = cfg.models["judge"]

    def _check(text: str) -> list[Violation]:
        # Deterministic tier first (no LLM), then the LLM judge; combine.
        return deterministic_check(text, retrieved) + judge(text, retrieved, llm, task=task)

    current = output
    violations = _check(current)
    regens = 0

    while violations and regenerate is not None and regens < max_regens:
        current = regenerate(current, violations)
        regens += 1
        violations = _check(current)

    passed = not violations
    return GateResult(
        passed=passed,
        violations=violations,
        regens=regens,
        escalated=not passed,
        final_output=current,
    )
