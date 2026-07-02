"""The provocation interview: elicit taste with small, non-leading scenarios.

Bootstrap (see `bootstrap.py`) mines Style from code the developer already
wrote. The interview mines the Style they have *not* yet had occasion to show,
by putting a few deliberately under-specified scenarios in front of them (a data
race, a tangle of cleanup conditionals, a resource that must be closed) and
asking them to either *do* it (write the code the way they would) or *declare* a
principle. A "do" answer yields a real Exemplar plus a Provisional Rule; a
"declare" answer yields a Confirmed Rule (the developer stated it outright, so
it does not need corroboration). This is a human-in-the-loop step; tests drive
it with a canned `transcript` instead of live prompts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..models import Exemplar, Layer, Rule, Status
from ..llm import get_llm


# The three provocations. Prompts are intentionally terse and non-leading: they
# describe a situation, never the "right" answer. `key` is the Rule topic a
# response to this scenario captures.
SCENARIOS: list[dict] = [
    {
        "id": "data-race",
        "key": "thread-safety",
        "prompt": (
            "Two threads increment the same counter. Show how you'd make the "
            "count correct, or state the principle you'd hold to."
        ),
        "java_snippet": (
            "class Counter {\n"
            "    private int count;\n"
            "    void increment() { count++; }\n"
            "    int get() { return count; }\n"
            "}\n"
        ),
    },
    {
        "id": "nested-cleanup",
        "key": "control-flow",
        "prompt": (
            "This method cleans up under several conditions and nests deeply. "
            "Rewrite it your way, or state the principle you'd hold to."
        ),
        "java_snippet": (
            "void handle(Session s) {\n"
            "    if (s != null) {\n"
            "        if (s.isOpen()) {\n"
            "            if (s.isDirty()) {\n"
            "                s.flush();\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
        ),
    },
    {
        "id": "resource-leak",
        "key": "resource-management",
        "prompt": (
            "This reads a file but may leak the stream on error. Show how you'd "
            "handle the resource, or state the principle you'd hold to."
        ),
        "java_snippet": (
            "String read(String path) throws IOException {\n"
            "    InputStream in = new FileInputStream(path);\n"
            "    return new String(in.readAllBytes());\n"
            "}\n"
        ),
    },
]

_BY_ID = {s["id"]: s for s in SCENARIOS}


@dataclass
class InterviewResult:
    """What the interview persisted: new Exemplars and new Rules."""

    exemplars_added: int
    rules_added: int


def load_transcript(path) -> dict:
    """Read a canned interview transcript (YAML) from disk."""
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def run_interview(
    store,
    *,
    language: str = "java",
    platform: str = "",
    transcript: dict | None = None,
    embedder=None,
    llm=None,
    input_fn=input,
    output_fn=print,
    adaptive: bool = False,
) -> InterviewResult:
    """Run the interview, persist the results, and report the counts.

    With `transcript` supplied the run is non-interactive (the HITL step already
    completed with test data); otherwise the scenarios are put to the developer
    via `input_fn`/`output_fn`. "do" answers become Provisional Rules plus
    Exemplars and "declare" answers become Confirmed Rules. An answer may also
    carry `narration` (a `/voice` stream-of-consciousness): the LLM extracts the
    principles the developer declares aloud, each a Confirmed Rule, and the raw
    narration is saved under ~/.disposition/interview.

    With `adaptive=True` and no transcript (ADR 0012), the fixed battery is
    followed by a short, LLM-driven round of gap-filling questions: the model
    weighs what is already KNOWN against what is still NEEDED and asks only the
    few follow-ups that close the biggest gaps. Each declared answer becomes a
    Confirmed Rule (provenance "interview:adaptive"). `adaptive=False` keeps the
    exact prior behaviour.
    """
    if transcript is not None:
        language = transcript.get("language", language)
        platform = transcript.get("platform", platform)
        answers = list(transcript.get("answers", []))
    else:
        answers = _collect(language, platform, input_fn, output_fn)

    new_rules: list[Rule] = []
    new_exemplars: list[Exemplar] = []
    for ans in answers:
        scenario = _BY_ID.get(ans.get("scenario"))
        if scenario is None:  # unknown scenario id: skip rather than guess
            continue
        mode = ans.get("mode")
        if mode == "do":
            code = (ans.get("code") or "").strip()
            if not code:
                continue
            source = f"interview:{scenario['id']}"
            new_exemplars.append(
                Exemplar(
                    id=Exemplar.make_id(source, 0, code),
                    code=code,
                    language=language,
                    layer=Layer.LANGUAGE,
                    source=source,
                    provenance="interview",
                    tags=["interview", scenario["id"]],
                )
            )
            # A demonstrated preference is real but unspoken -> Provisional.
            text = (ans.get("principle") or "").strip() or (
                f"Follow the demonstrated approach for {scenario['key']} "
                f"(see interview scenario '{scenario['id']}')."
            )
            new_rules.append(
                Rule(
                    key=scenario["key"],
                    text=text,
                    status=Status.PROVISIONAL,
                    layer=Layer.LANGUAGE,
                    confidence=0.5,
                    provenance="interview",
                    tags=["interview", scenario["id"]],
                )
            )
        elif mode == "declare":
            principle = (ans.get("principle") or "").strip()
            if not principle:
                continue
            # A stated principle needs no corroboration -> Confirmed.
            new_rules.append(
                Rule(
                    key=scenario["key"],
                    text=principle,
                    status=Status.CONFIRMED,
                    layer=Layer.LANGUAGE,
                    confidence=0.9,
                    provenance="interview:declared",
                    tags=["interview", scenario["id"]],
                )
            )

        # A narration (via /voice) is stream-of-consciousness reasoning. The
        # principles the developer states aloud are Confirmed Rules; the raw
        # text is kept for the record. This is additive to any do/declare above.
        narration = (ans.get("narration") or "").strip()
        if narration:
            if llm is None:
                llm = get_llm()
            _persist_narration(store, scenario["id"], narration)
            for principle in _extract_principles(narration, scenario, llm):
                new_rules.append(
                    Rule(
                        key=principle["key"],
                        text=principle["text"],
                        status=Status.CONFIRMED,
                        layer=Layer.LANGUAGE,
                        confidence=0.85,
                        provenance="interview:voice",
                        tags=["interview", "voice", scenario["id"]],
                    )
                )

    # Adaptive gap-filling: only when driven live (a transcript is a completed,
    # fixed HITL run and is left exactly as before).
    if adaptive and transcript is None:
        if llm is None:
            llm = get_llm()
        new_rules.extend(
            _collect_adaptive(store, language, llm, input_fn, output_fn)
        )

    exemplars_added = _persist_exemplars(store, language, new_exemplars, embedder)
    rules_added = store.merge_rules(Layer.LANGUAGE, new_rules, language)
    return InterviewResult(exemplars_added=exemplars_added, rules_added=rules_added)


# -- adaptive gap-model (ADR 0012) ------------------------------------------


def adaptive_followups(
    store, *, language: str = "java", llm=None, max_questions: int = 3
) -> list[dict]:
    """Propose the few follow-ups that best close the gaps in a known Style.

    Rather than re-asking the fixed battery, we hand the model what is already
    KNOWN (the developer's Active Style) and ask it to reason about what is still
    NEEDED: the biggest unsettled style topics. It returns up to `max_questions`
    targeted, non-leading questions -- the most ground covered in the fewest
    questions. Each item is ``{"key": short-kebab-topic, "question": prompt}``.
    """
    llm = llm or get_llm()
    known = store.active_style(language)  # merged, winning Rules = what we KNOW
    known_lines = "\n".join(f"- {r.key}: {r.text}" for r in known) or "(nothing yet)"
    topics = ", ".join(sorted({s["key"] for s in SCENARIOS}))
    prompt = (
        "You are eliciting a developer's coding style with as few questions as "
        "possible. Below is what is ALREADY KNOWN about their style. Find the "
        "biggest GAPS -- important style topics not yet settled -- and propose up "
        f"to {max_questions} targeted, non-leading follow-up questions that fill "
        "the most ground in the fewest questions. Do not re-ask what is already "
        "known, and never hint at the 'right' answer inside the question.\n\n"
        f"LANGUAGE: {language}\nCOMMON TOPICS: {topics}\n\n"
        f"ALREADY KNOWN:\n{known_lines}\n\n"
        'Return a JSON array of objects {"key": short-kebab-topic, '
        '"question": one neutral question}.'
    )
    data = llm.json(prompt)
    items = data.get("questions", []) if isinstance(data, dict) else data
    out: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        key = str(item.get("key") or "").strip()
        if not question or not key:  # both fields required to be actionable
            continue
        out.append({"key": key, "question": question})
        if len(out) >= max_questions:
            break
    return out


def _collect_adaptive(store, language, llm, input_fn, output_fn) -> list[Rule]:
    """Ask each proposed follow-up; a declared answer becomes a Confirmed Rule."""
    rules: list[Rule] = []
    for followup in adaptive_followups(store, language=language, llm=llm):
        output_fn("\n" + followup["question"])
        answer = input_fn("Principle (blank to skip): ").strip()
        if not answer:  # a skipped gap stays a gap, not a hollow rule
            continue
        rules.append(
            Rule(
                key=followup["key"],
                text=answer,
                status=Status.CONFIRMED,
                layer=Layer.LANGUAGE,
                confidence=0.9,
                provenance="interview:adaptive",
                tags=["interview", "adaptive"],
            )
        )
    return rules


# -- narration (/voice) -----------------------------------------------------


def _extract_principles(narration: str, scenario: dict, llm) -> list[dict]:
    """Pull the style principles a developer declares in a spoken narration."""
    prompt = (
        "A developer narrated their thinking aloud while solving a coding "
        "scenario. Extract only the style principles they DECLARE (things they "
        "say they always or never do, or clearly prefer). Ignore questions, "
        "hedges, and one-off observations. Return a JSON array of objects "
        '{"key": short-kebab-topic, "text": one imperative sentence}.\n\n'
        f"SCENARIO: {scenario['prompt']}\n\nNARRATION:\n{narration}"
    )
    data = llm.json(prompt)
    items = data.get("principles", []) if isinstance(data, dict) else data
    principles: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            continue
        key = str(item.get("key") or scenario["key"]).strip() or scenario["key"]
        principles.append({"key": key, "text": str(item["text"]).strip()})
    return principles


def _persist_narration(store, scenario_id: str, narration: str) -> None:
    """Append the raw narration transcript to the interview record."""
    directory = store.root / "interview"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{scenario_id}.md"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(narration.strip() + "\n\n---\n\n")


# -- persistence ------------------------------------------------------------


def _persist_exemplars(store, language: str, new: list[Exemplar], embedder) -> int:
    """Add Exemplars (dedup by id) and rebuild the Language exemplar index."""
    if not new:
        return 0
    before = len(store.load_exemplars(Layer.LANGUAGE, language))
    merged = store.add_exemplars(Layer.LANGUAGE, new, language)
    store.rebuild_index(Layer.LANGUAGE, language, embedder=embedder)
    return len(merged) - before


# -- interactive fallback ---------------------------------------------------


def _collect(language, platform, input_fn, output_fn) -> list[dict]:
    """Prompt the developer through each scenario, returning transcript answers."""
    if not platform:
        platform = input_fn("Platform (e.g. android, backend): ").strip()
    language = input_fn(f"Language [{language}]: ").strip() or language

    answers: list[dict] = []
    for scenario in SCENARIOS:
        output_fn("\n" + scenario["prompt"])
        output_fn(scenario["java_snippet"])
        mode = input_fn("[d]o it, or de[c]lare a principle? ").strip().lower()
        if mode.startswith("c"):
            principle = input_fn("Principle: ").strip()
            answers.append(
                {"scenario": scenario["id"], "mode": "declare", "principle": principle}
            )
        else:
            output_fn("Enter your code, end with a single '.' on its own line:")
            lines: list[str] = []
            while True:
                line = input_fn("")
                if line.strip() == ".":
                    break
                lines.append(line)
            answers.append(
                {"scenario": scenario["id"], "mode": "do", "code": "\n".join(lines)}
            )
    return answers
