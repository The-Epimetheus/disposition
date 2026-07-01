"""Small helpers for running git as a subprocess.

Shared by the capture modules (bootstrap, provenance, ambient) so they agree on
one degrade-gracefully policy: any git failure yields empty output rather than
raising, because a missing or malformed repo should not crash capture.
"""

from __future__ import annotations

import subprocess


def git_out(repo: str, args: list[str]) -> str:
    """Run `git -C repo <args>` and return stdout, or "" on any failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def git_lines(repo: str, args: list[str]) -> list[str]:
    """Run a git command, returning stripped non-empty stdout lines."""
    return [line.strip() for line in git_out(repo, args).splitlines() if line.strip()]
