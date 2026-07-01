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
from ..embeddings import get_embedder
from ..index import VectorIndex


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
    input_fn=input,
    output_fn=print,
) -> InterviewResult:
    """Run the interview, persist the results, and report the counts.

    With `transcript` supplied the run is non-interactive (the HITL step already
    completed with test data); otherwise the scenarios are put to the developer
    via `input_fn`/`output_fn`. Either way, "do" answers become Provisional
    Rules plus Exemplars and "declare" answers become Confirmed Rules.
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

    exemplars_added = _persist_exemplars(store, language, new_exemplars, embedder)
    rules_added = _persist_rules(store, language, new_rules)
    return InterviewResult(exemplars_added=exemplars_added, rules_added=rules_added)


# -- persistence ------------------------------------------------------------


def _persist_rules(store, language: str, new_rules: list[Rule]) -> int:
    """Merge new Rules into the Language layer by key; return the net added."""
    if not new_rules:
        return 0
    existing = store.load_rules(Layer.LANGUAGE, language)
    by_key = {r.key: r for r in existing}
    before = len(by_key)
    for rule in new_rules:
        by_key[rule.key] = rule  # a fresh answer supersedes a prior one
    store.save_rules(Layer.LANGUAGE, list(by_key.values()), language)
    return len(by_key) - before


def _persist_exemplars(store, language: str, new: list[Exemplar], embedder) -> int:
    """Add Exemplars (dedup by id) and rebuild the Language exemplar index."""
    if not new:
        return 0
    before = len(store.load_exemplars(Layer.LANGUAGE, language))
    merged = store.add_exemplars(Layer.LANGUAGE, new, language)
    added = len(merged) - before

    # Rebuild the derived vector index over every Language exemplar so the new
    # ones are retrievable. The index is a cache; a full rebuild keeps it honest.
    embedder = embedder or get_embedder()
    index = VectorIndex(embedder.dim)
    if merged:
        vectors = embedder.embed([ex.code for ex in merged])
        index.add_many(
            [
                (ex.id, vectors[i], {"source": ex.source, "provenance": ex.provenance})
                for i, ex in enumerate(merged)
            ]
        )
    index.save(store.index_dir(Layer.LANGUAGE, language))
    return added


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
