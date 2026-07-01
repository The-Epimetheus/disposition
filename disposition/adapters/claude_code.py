"""Claude Code adapter: Forced Injection into CLAUDE.md, plus MCP registration.

This is the "no-inference-time hook" surface (ADR 0009). We render the Active
Style as a legible Markdown block and splice it into the repo's CLAUDE.md so
Claude Code reads it as project instructions. The block is fenced by a marker
comment so re-running replaces it in place rather than piling up duplicates.

`register_mcp` only returns the command to wire the Disposition MCP server; it
does not shell out, so the caller decides when (and whether) to run it.
"""

from __future__ import annotations

from pathlib import Path

from ..models import Exemplar, Rule
from ..store import Store

# The marked block is delimited by these HTML comments. Everything between them
# is ours to overwrite; everything outside is the user's and stays untouched.
START_MARKER = "<!-- disposition:start -->"
END_MARKER = "<!-- disposition:end -->"


def _rules_markdown(rules: list[Rule]) -> list[str]:
    """One bullet per Rule, tagging Provisional ones so their weight is clear."""
    if not rules:
        return ["_No style rules captured yet._"]
    lines: list[str] = []
    for rule in rules:
        # Confirmed rules steer silently; flag the softer Provisional ones.
        suffix = "" if rule.status.value == "confirmed" else " _(provisional)_"
        lines.append(f"- **{rule.key}**: {rule.text}{suffix}")
    return lines


def _exemplars_markdown(exemplars: list[Exemplar], language: str) -> list[str]:
    """A few fenced code blocks so the model sees the tacit texture, not just rules."""
    if not exemplars:
        return []
    lines = ["", "### Exemplars", ""]
    for ex in exemplars:
        label = ex.source or ex.provenance or ex.id
        lines.append(f"_{label}_")
        lines.append(f"```{language}")
        lines.append(ex.code.strip("\n"))
        lines.append("```")
        lines.append("")
    return lines


def generate_claude_md_section(
    store: Store,
    *,
    language: str = "java",
    task: str | None = None,
    embedder=None,
    k_exemplars: int = 3,
) -> str:
    """Render the Active Style (and a few exemplars) as a Markdown block.

    Without a `task` we emit the whole merged Active Style and a handful of
    exemplars. With a `task` we defer to retrieval so the block is scoped to
    what the current job actually needs (dynamic injection, strategy B).
    """
    if task is not None:
        # Import lazily: retrieval is a sibling component, not a hard dep here.
        from ..retrieval import retrieve

        result = retrieve(
            store,
            task=task,
            language=language,
            k_exemplars=k_exemplars,
            embedder=embedder,
        )
        rules = result.rules
        exemplars = result.exemplars
    else:
        rules = store.active_style(language)
        exemplars = store.all_exemplars(language)[:k_exemplars]

    lines = [
        START_MARKER,
        "## Coding Style (Disposition)",
        "",
        f"Honor this developer's confirmed style for `{language}`. "
        "These are directives, not suggestions.",
        "",
        "### Rules",
        "",
    ]
    lines += _rules_markdown(rules)
    lines += _exemplars_markdown(exemplars, language)
    lines.append(END_MARKER)
    return "\n".join(lines).rstrip() + "\n"


def write_claude_md(
    section: str,
    *,
    repo: str = ".",
    marker: str = START_MARKER,
) -> Path:
    """Idempotently insert or replace the marked block in <repo>/CLAUDE.md.

    If a block delimited by `marker`..`END_MARKER` already exists we swap its
    body; otherwise we append the section. Content outside the markers is left
    exactly as the user wrote it.
    """
    path = Path(repo) / "CLAUDE.md"
    block = section.strip("\n")
    existing = path.read_text(encoding="utf-8") if path.exists() else ""

    start = existing.find(marker)
    end = existing.find(END_MARKER)
    if start != -1 and end != -1 and end > start:
        # Replace the old block in place, preserving surrounding text.
        end += len(END_MARKER)
        updated = existing[:start] + block + existing[end:]
    elif existing.strip():
        # Append after existing content with a blank line separator.
        updated = existing.rstrip("\n") + "\n\n" + block + "\n"
    else:
        updated = block + "\n"

    path.write_text(updated, encoding="utf-8")
    return path


def register_mcp(*, name: str = "disposition") -> list[str]:
    """Return the `claude mcp add` command that wires the Disposition server.

    We return the argv rather than executing it: registration is an explicit,
    user-visible action, and returning the list keeps this pure and testable.
    """
    return ["claude", "mcp", "add", name, "--", "disposition", "serve"]
