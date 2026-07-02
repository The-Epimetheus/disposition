"""The shared PROJECT layer: a repo's own house style (ADR 0011, ADR 0002).

Unlike the private Personal and Language layers (which live under
~/.disposition and travel with the developer), house style belongs to the
codebase. So it is auto-derived from the repo, maintainer-confirmed, and
committed IN the repo at <repo>/.disposition/rules.yaml, where it travels with
the code and every contributor's agent picks it up.

Derivation mirrors induction: mine the repo's tracked *.java, chunk them, and
ask the LLM to distill candidate rules. Because unconfirmed house style is only
a weak prior, derived rules start PROVISIONAL -- under the two-key precedence a
Provisional Project rule does NOT override a Confirmed Personal one. A
maintainer must Confirm a rule before it outranks a developer's own settled
taste (see cascade.py: status is the first precedence key, layer the second).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .gitutil import git_lines
from .java import chunk_java_file
from .llm import get_llm
from .models import Layer, Rule, Status
from .store import _today

# House style lives inside the repo so it is versioned alongside the code.
_PROJECT_DIR = ".disposition"
_RULES_FILE = "rules.yaml"

# A derived house-style candidate needs a name to be usable; empty keys drop.
_DERIVE_SYSTEM = (
    "You distill a codebase's shared house style into rules. You are "
    "adversarial: propose only rules the code actually supports, and mark as "
    "mechanical any rule that is purely syntactic (formatting, casing, brace "
    "placement, import ordering) rather than a design judgement."
)


def _rules_path(repo: str | Path) -> Path:
    """The committed house-style file for a repo: <repo>/.disposition/rules.yaml."""
    return Path(repo) / _PROJECT_DIR / _RULES_FILE


def _tracked_java(repo: str | Path, author: str | None) -> list[str]:
    """Relative paths of tracked *.java files, optionally scoped to `author`."""
    tracked = git_lines(str(repo), ["ls-files", "*.java"])
    if not author:
        return tracked
    touched = set(
        git_lines(
            str(repo),
            ["log", f"--author={author}", "--name-only", "--pretty=format:"],
        )
    )
    return [path for path in tracked if path in touched]


def derive_project(
    repo: str | Path,
    *,
    language: str = "java",
    author: str | None = None,
    llm=None,
    limit: int = 120,
) -> list[Rule]:
    """Mine `repo`'s tracked source and distill candidate PROJECT rules.

    Lists tracked *.java (optionally narrowed to `author`), chunks each into
    method/class units, and asks the LLM to infer the house style they imply
    (same JSON shape as induction). Every derived Rule lands in the PROJECT
    layer as PROVISIONAL: unconfirmed house style is a weak prior and must be
    blessed by a maintainer before it steers over a developer's own taste.
    """
    llm = llm or get_llm()
    files = _tracked_java(repo, author)[:limit]

    blocks: list[str] = []
    for rel in files:
        abs_path = str(Path(repo) / rel)
        for chunk in chunk_java_file(abs_path):
            blocks.append(f"// {rel}:{chunk.start_line}\n{chunk.code}")
    if not blocks:
        return []

    joined = "\n\n".join(blocks)
    prompt = (
        f"Here are {len(blocks)} {language} code units from one repository. "
        "Infer the shared house-style rules they imply. Return a JSON array of "
        'objects: {"key": short-slug, "text": one-sentence rule, '
        '"confidence": 0..1, "mechanical": true|false}.\n\n'
        f"{joined}"
    )
    raw = llm.json(prompt, system=_DERIVE_SYSTEM, max_tokens=8192)
    # Tolerate either a bare array or a wrapping object with a "rules" key.
    items = raw.get("rules", []) if isinstance(raw, dict) else raw

    rules: list[Rule] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        mechanical = bool(item.get("mechanical", False))
        rules.append(
            Rule(
                key=str(item["key"]),
                text=str(item.get("text", "")),
                status=Status.PROVISIONAL,
                layer=Layer.PROJECT,
                confidence=float(item.get("confidence", 0.5)),
                provenance="project-derive",
                tags=["mechanical"] if mechanical else [],
            )
        )
    return rules


def save_project_rules(repo: str | Path, rules: list[Rule]) -> Path:
    """Write `rules` to the repo's committed <repo>/.disposition/rules.yaml."""
    path = _rules_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "rules": [
            {
                "key": rule.key,
                "text": rule.text,
                "status": rule.status.value,
                "confidence": rule.confidence,
                "provenance": rule.provenance,
                "tags": rule.tags,
                "created": rule.created or _today(),
            }
            for rule in rules
        ]
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path


def load_project_rules(repo: str | Path, language: str = "java") -> list[Rule]:
    """Read the repo's committed house-style rules; layer forced to PROJECT.

    The file lives inside the repo and may be hand-edited, so like the store we
    never let it claim a layer it does not live in: every rule loads as PROJECT.
    """
    path = _rules_path(repo)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    rules: list[Rule] = []
    for item in data.get("rules", []):
        rules.append(
            Rule(
                key=item["key"],
                text=item["text"],
                status=Status(item.get("status", "provisional")),
                layer=Layer.PROJECT,
                confidence=float(item.get("confidence", 0.5)),
                provenance=item.get("provenance", ""),
                tags=list(item.get("tags", [])),
                created=item.get("created", ""),
            )
        )
    return rules


def confirm_project(
    repo: str | Path,
    *,
    language: str = "java",
    auto: bool = False,
    input_fn=input,
    output_fn=print,
) -> dict:
    """A maintainer blesses the provisional house-style rules, then persists.

    `auto=True` (the non-interactive path) confirms every provisional rule.
    Interactively, the maintainer confirms/edits/rejects each one; anything
    left unreviewed stays Provisional (safe, non-steering). Returns the count
    of rules now Confirmed.
    """
    rules = load_project_rules(repo, language)
    kept: list[Rule] = []
    confirmed = 0

    for rule in rules:
        # Already-confirmed rules are left as-is and re-counted.
        if rule.status is Status.CONFIRMED:
            kept.append(rule)
            confirmed += 1
            continue

        if auto:
            rule.status = Status.CONFIRMED
            kept.append(rule)
            confirmed += 1
            continue

        status, text = _prompt_one(rule, input_fn=input_fn, output_fn=output_fn)
        if status is None:  # rejected: drop from the house style
            continue
        rule.text = text
        rule.status = status
        kept.append(rule)
        if status is Status.CONFIRMED:
            confirmed += 1

    save_project_rules(repo, kept)
    return {"confirmed": confirmed}


def _prompt_one(rule: Rule, *, input_fn, output_fn) -> tuple[Status | None, str]:
    """Interactively review one house-style rule. Returns (status|None, text)."""
    output_fn(f"\nHouse rule [{rule.key}] (confidence {rule.confidence:.2f})")
    output_fn(f"  {rule.text}")
    choice = input_fn("[c]onfirm / [e]dit / [p]rovisional / [r]eject? ").strip().lower()
    if choice.startswith("r"):
        return None, rule.text
    if choice.startswith("e"):
        edited = input_fn("  new text: ").strip() or rule.text
        return Status.CONFIRMED, edited
    if choice.startswith("c"):
        return Status.CONFIRMED, rule.text
    # Anything else (including empty) leaves it Provisional and non-steering.
    return Status.PROVISIONAL, rule.text
