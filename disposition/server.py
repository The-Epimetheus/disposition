"""The Disposition MCP server (hello-world for M0).

This is the SSP delivery path (ADR 0001). For M0 it exposes a single tool that
returns the current Active Style as text, so a host like Claude Code can pull
it on demand. Forced Injection and the Verification Gate (ADR 0003) arrive in
later milestones; this proves the wiring end to end.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .config import default_root
from .store import Store

mcp = FastMCP("disposition")


@mcp.tool()
def active_style(language: str = "java") -> str:
    """Return the developer's Active Style (merged Rules) for steering.

    Args:
        language: which Language layer to merge with Personal (default "java").
    """
    root = default_root()
    if not root.exists():
        return "Disposition is not initialized. Run `disposition init` first."

    rules = Store(root).active_style(language)
    if not rules:
        return (
            "No style rules captured yet. Run onboarding (M1) to populate the "
            "profile."
        )

    lines = [f"Active Style (personal + {language}):"]
    for rule in rules:
        lines.append(f"- ({rule.status.value}, {rule.layer.value}) {rule.text}")
    return "\n".join(lines)


def main() -> None:
    """Run the server over stdio (the default FastMCP transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
