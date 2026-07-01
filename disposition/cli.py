"""The Disposition CLI shell.

M0 ships four commands: `version`, `init` (scaffold + default config),
`status` (show the Active Style), and `serve` (start the MCP server). Later
milestones add onboarding, triage, and `reinforce`.
"""

from __future__ import annotations

import typer

from . import __version__
from .config import Config, default_root
from .models import Layer
from .store import Store

app = typer.Typer(
    help="Disposition: steer an AI coding tool to write in your style.",
    no_args_is_help=True,
    add_completion=False,
)


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
        config = Config.load(root)
        typer.echo(f"Config already present at {config_path}")
    else:
        config = Config.load(root)
        config.write()
        typer.echo(f"Wrote default config to {config_path}")

    Store(root).scaffold(language)
    typer.echo(f"Scaffolded profiles for 'personal' and '{language}' under {root}")
    typer.echo("Next: onboarding (Bootstrap + Interview) lands in M1.")


@app.command()
def status(
    language: str = typer.Option("java", help="Language layer to report on.")
) -> None:
    """Show the merged Active Style for a language."""
    root = default_root()
    if not root.exists():
        typer.echo("Not initialized. Run `disposition init` first.")
        raise typer.Exit(code=1)

    store = Store(root)
    rules = store.active_style(language)
    typer.echo(f"Active Style (personal + {language}):")
    if not rules:
        typer.echo("  (no rules yet - capture happens in M1)")
        return
    for rule in rules:
        typer.echo(
            f"  [{rule.status.value:<11} {rule.layer.value:<8}] "
            f"{rule.key}: {rule.text}"
        )


@app.command()
def serve() -> None:
    """Start the Disposition MCP server over stdio."""
    from .server import main as serve_main

    serve_main()


if __name__ == "__main__":
    app()
