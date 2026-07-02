"""The Disposition CLI shell.

M0 shipped `version`, `init`, `status`, and `serve`. M1 wires the capture and
steering pipeline into the shell: `bootstrap` and `interview` (onboarding),
`induce` (distillation + triage), `inject` (Forced Injection into CLAUDE.md),
`verify` (the Verification Gate over a file), and `reinforce` (learn from an
in-editor correction). Each command is a thin adapter over a component module.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import __version__
from . import aging
from . import coldstart
from . import project as project_mod
from .adapters import claude_code
from .capture import ambient as ambient_mod
from .capture import bootstrap as bootstrap_mod
from .capture import correction as correction_mod
from .capture import interview as interview_mod
from .capture import provenance as provenance_mod
from .config import Config, default_root
from .gate import judge as gate_judge
from .gate import llm_regenerator as gate_regenerator
from .gate import verify as gate_verify
from .induction import consolidate as consolidate_fn
from .induction import induce as induce_fn
from .induction import triage as triage_fn
from .llm import get_llm
from .retrieval import retrieve as retrieve_fn
from .store import Store

app = typer.Typer(
    help="Disposition: steer an AI coding tool to write in your style.",
    no_args_is_help=True,
    add_completion=False,
)


def _store() -> Store:
    """Open the store at ~/.disposition, erroring if it is not initialized."""
    root = default_root()
    if not root.exists():
        typer.echo("Not initialized. Run `disposition init` first.")
        raise typer.Exit(code=1)
    return Store(root)


@app.command()
def version() -> None:
    """Print the Disposition version."""
    typer.echo(__version__)


@app.command()
def init(language: str = typer.Option("java", help="Language layer to set up.")) -> None:
    """Set up ~/.disposition: write config and scaffold the profile tree."""
    root = default_root()
    config_path = root / "config.toml"
    if config_path.exists():
        Config.load(root)
        typer.echo(f"Config already present at {config_path}")
    else:
        config = Config.load(root)
        config.write()
        typer.echo(f"Wrote default config to {config_path}")

    Store(root).scaffold(language)
    typer.echo(f"Scaffolded profiles for 'personal' and '{language}' under {root}")
    typer.echo("Next: run `disposition bootstrap <repo>` or `disposition interview`.")


@app.command()
def status(
    language: str = typer.Option("java", help="Language layer to report on."),
    repo: str = typer.Option(
        None, "--repo", help="Also merge this repo's PROJECT house style."
    ),
) -> None:
    """Show the merged Active Style for a language (and optionally a repo)."""
    store = _store()
    rules = store.active_style(language, repo)
    layers = f"personal + {language}" + (" + project" if repo else "")
    typer.echo(f"Active Style ({layers}):")
    if not rules:
        typer.echo("  (no rules yet - run bootstrap/interview/induce)")
        return
    for rule in rules:
        typer.echo(
            f"  [{rule.status.value:<11} {rule.layer.value:<8}] "
            f"{rule.key}: {rule.text}"
        )


@app.command()
def bootstrap(
    repo: str = typer.Argument(..., help="Path to the repository to mine."),
    author: str = typer.Option(None, "--author", help="Restrict to this author's files."),
    language: str = typer.Option("java", help="Language layer to populate."),
) -> None:
    """Mine an existing repo for exemplars and build the retrieval index."""
    store = _store()
    result = bootstrap_mod.bootstrap(store, repo, author=author, language=language)
    typer.echo(
        f"Bootstrap: scanned {result.files_scanned} files, "
        f"added {result.exemplars_added} exemplars, "
        f"index now holds {result.index_size}."
    )


@app.command()
def interview(
    transcript: str = typer.Option(
        None, "--transcript", help="Path to a canned transcript (YAML) for non-interactive runs."
    ),
    language: str = typer.Option("java", help="Language layer to populate."),
    platform: str = typer.Option("", help="Target platform (e.g. android, backend)."),
    adaptive: bool = typer.Option(
        False, "--adaptive", help="Follow the fixed battery with LLM-driven gap-filling questions."
    ),
) -> None:
    """Run the provocation interview, live or from a canned transcript."""
    store = _store()
    data = interview_mod.load_transcript(transcript) if transcript else None
    result = interview_mod.run_interview(
        store, language=language, platform=platform, transcript=data, adaptive=adaptive
    )
    typer.echo(
        f"Interview: added {result.rules_added} rules and "
        f"{result.exemplars_added} exemplars."
    )


@app.command()
def induce(
    language: str = typer.Option("java", help="Language layer to distill."),
    auto: bool = typer.Option(False, "--auto", help="Non-interactive triage (test/CI path)."),
) -> None:
    """Distill candidate rules from exemplars, then triage them into the Profile."""
    store = _store()
    candidates = induce_fn(store, language=language)
    if not candidates:
        typer.echo("No exemplars to induce from yet. Run bootstrap/interview first.")
        return
    counts = triage_fn(store, candidates, language=language, auto=auto)
    typer.echo(
        f"Induction: {counts['confirmed']} confirmed, "
        f"{counts['provisional']} provisional."
    )


@app.command()
def consolidate(
    language: str = typer.Option("java", help="Language layer to consolidate."),
) -> None:
    """Merge near-duplicate rules in the Profile into canonical ones."""
    store = _store()
    counts = consolidate_fn(store, language=language)
    typer.echo(
        f"Consolidated {counts['before']} rules into {counts['after']}."
    )


@app.command()
def inject(
    repo: str = typer.Option(".", "--repo", help="Repo whose CLAUDE.md to update."),
    task: str = typer.Option(None, "--task", help="Scope injection to this task via retrieval."),
    language: str = typer.Option("java", help="Language layer to inject."),
    strategy: str = typer.Option(
        None, "--strategy", help="Injection policy: A full / B dynamic / C hybrid (default from config)."
    ),
) -> None:
    """Write the Active Style into <repo>/CLAUDE.md and print the MCP command."""
    store = _store()
    strat = strategy or Config.load().injection.get("strategy", "B")
    section = claude_code.generate_claude_md_section(
        store, language=language, task=task, strategy=strat, repo=repo
    )
    path = claude_code.write_claude_md(section, repo=repo)
    typer.echo(f"Wrote Disposition block to {path}")
    typer.echo("Register the MCP server with:")
    typer.echo("  " + " ".join(claude_code.register_mcp()))


@app.command()
def verify(
    file: str = typer.Option(..., "--file", help="File whose contents to judge."),
    task: str = typer.Option("", "--task", help="Task the output was meant to satisfy."),
    language: str = typer.Option("java", help="Language layer to judge against."),
    repo: str = typer.Option(
        None, "--repo", help="Also judge against this repo's PROJECT house style."
    ),
    judge_only: bool = typer.Option(
        False, "--judge-only", help="One judge pass, report only, no regeneration."
    ),
    write: bool = typer.Option(
        False, "--write", help="Overwrite FILE with the regenerated output when the gate fixes it."
    ),
) -> None:
    """Run the Verification Gate over a file: judge, regenerate, escalate."""
    store = _store()
    output = Path(file).read_text(encoding="utf-8")
    retrieved = retrieve_fn(store, task=task, language=language, repo=repo)
    llm = get_llm()

    if judge_only:
        violations = gate_judge(output, retrieved, llm, task=task)
        if not violations:
            typer.echo("PASS: output is inside the style envelope.")
            return
        typer.echo(f"FAIL: {len(violations)} violation(s):")
        for v in violations:
            typer.echo(f"  - [{v.cite}] {v.detail}")
        raise typer.Exit(code=1)

    # The full Gate: deterministic tier + judge, regenerating on violations up
    # to the configured budgets.max_regens, then escalating to the human.
    result = gate_verify(
        output,
        retrieved,
        llm=llm,
        task=task,
        regenerate=gate_regenerator(llm, retrieved, task=task),
    )

    if result.passed and result.regens == 0:
        typer.echo("PASS: output is inside the style envelope.")
        return

    if result.passed:
        typer.echo(f"PASS after {result.regens} regeneration(s).")
        if write:
            Path(file).write_text(result.final_output, encoding="utf-8")
            typer.echo(f"Wrote the corrected output back to {file}")
        else:
            typer.echo("Corrected output (use --write to save it):")
            typer.echo(result.final_output)
        return

    typer.echo(
        f"ESCALATE: still {len(result.violations)} violation(s) "
        f"after {result.regens} regeneration(s):"
    )
    for v in result.violations:
        typer.echo(f"  - [{v.cite}] {v.detail}")
    raise typer.Exit(code=1)


@app.command()
def reinforce(
    ai: str = typer.Option(..., "--ai", help="File with the original AI-generated code."),
    edited: str = typer.Option(..., "--edited", help="File with the developer's edit."),
    language: str = typer.Option("java", help="Language layer to reinforce."),
) -> None:
    """Learn from one AI-vs-edited diff, keeping only behavior-preserving edits."""
    store = _store()
    ai_code = Path(ai).read_text(encoding="utf-8")
    edited_code = Path(edited).read_text(encoding="utf-8")
    result = correction_mod.reinforce(
        store, ai_code=ai_code, edited_code=edited_code, language=language
    )
    if not result.accepted:
        typer.echo(f"Rejected (behavior-changing): {result.reason}")
        return
    typer.echo(
        f"Accepted: rule_added={result.rule_added}, "
        f"exemplar_added={result.exemplar_added} ({result.reason})"
    )


@app.command()
def track(
    file: str = typer.Argument(..., help="Repo-relative file with AI-generated code."),
    start: int = typer.Option(..., "--start", help="First line (1-based) of the span."),
    end: int = typer.Option(..., "--end", help="Last line of the span."),
    repo: str = typer.Option(".", "--repo", help="Repo root the file lives in."),
) -> None:
    """Record a span of AI-generated code to watch for later corrections."""
    store = _store()
    span = provenance_mod.record_span(store, repo, file, start, end)
    typer.echo(f"Tracked {file}:{start}-{end} (span {span.id}).")


@app.command()
def watch(
    repo: str = typer.Option(None, "--repo", help="Limit the scan to this repo."),
    language: str = typer.Option("java", help="Language layer to reinforce."),
) -> None:
    """Scan tracked spans for edits, capturing behavior-preserving corrections."""
    store = _store()
    result = provenance_mod.scan(store, repo, language=language)
    typer.echo(
        f"Watch: {result.corrections} correction(s), {result.excluded} excluded, "
        f"{result.pending} unchanged."
    )


@app.command()
def observe(
    repo: str = typer.Argument(..., help="Repo to capture new commits from."),
    author: str = typer.Option(None, "--author", help="Restrict to this author."),
    language: str = typer.Option("java", help="Language layer to enrich."),
) -> None:
    """Capture code authored since the last run as ambient style signal."""
    store = _store()
    result = ambient_mod.capture(store, repo, author=author, language=language)
    if result.baseline:
        typer.echo(
            f"Ambient baseline set at {result.watermark[:10]}; "
            "capturing forward from here."
        )
        return
    typer.echo(
        f"Ambient: {result.commits} commit(s), {result.files} file(s), "
        f"{result.exemplars_added} exemplars added."
    )


@app.command()
def age(
    language: str = typer.Option("java", help="Language layer to age."),
) -> None:
    """Decay stale Provisional Rules by age and drop those past the floor."""
    store = _store()
    counts = aging.age_profile(store, language=language)
    typer.echo(f"Aged {counts['aged']} rules, dropped {counts['dropped']}.")


@app.command()
def drift(
    language: str = typer.Option("java", help="Language layer to check for drift."),
) -> None:
    """Surface Delta Queries where recent code contradicts a Confirmed Rule."""
    store = _store()
    queries = aging.detect_drift(store, language=language, llm=get_llm())
    if not queries:
        typer.echo("No drift detected.")
        return
    for q in queries:
        typer.echo(f"  [{q.rule_key}] {q.question}")


@app.command()
def project(
    repo: str = typer.Argument(..., help="Repo whose house style to derive."),
    author: str = typer.Option(None, "--author", help="Restrict derivation to this author's files."),
    language: str = typer.Option("java", help="Language layer to derive against."),
    auto: bool = typer.Option(False, "--auto", help="Confirm every derived rule (non-interactive)."),
) -> None:
    """Derive the repo's shared PROJECT house style, then confirm and commit it."""
    store = _store()
    rules = project_mod.derive_project(repo, language=language, author=author)
    if not rules:
        typer.echo("No source found to derive house style from.")
        return
    path = project_mod.save_project_rules(repo, rules)
    counts = project_mod.confirm_project(repo, language=language, auto=auto)
    typer.echo(
        f"Project: derived {len(rules)} rule(s), {counts['confirmed']} confirmed."
    )
    typer.echo(f"Wrote house style to {path}")


@app.command()
def archetypes() -> None:
    """List the available cold-start archetypes."""
    for name in coldstart.list_archetypes():
        typer.echo(f"  {name}")


@app.command()
def archetype(
    name: str = typer.Argument(..., help="Archetype to seed into the Language layer."),
    language: str = typer.Option("java", help="Language layer to seed."),
) -> None:
    """Seed a cold-start archetype's Rules into the Language layer."""
    store = _store()
    try:
        added = coldstart.apply_archetype(store, name, language=language)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)
    typer.echo(f"Archetype '{name}': added {added} new rule(s).")


@app.command()
def serve() -> None:
    """Start the Disposition MCP server over stdio."""
    from .server import main as serve_main

    serve_main()


if __name__ == "__main__":
    app()
