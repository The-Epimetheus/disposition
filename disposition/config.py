"""Load and write ~/.disposition/config.toml.

Reading uses the standard library `tomllib` (Python 3.11+). Writing uses a tiny
local renderer so M0 needs no TOML-writing dependency. The schema is flat
(tables of scalar values), which keeps the renderer safe and simple.
"""

from __future__ import annotations

import tomllib
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

# Defaults. `injection.strategy = "B"` is the v1 choice: dynamic retrieval
# (Q19). `budgets.max_regens = 3` is the Verification Gate cap (ADR 0006).
DEFAULT_CONFIG: dict[str, dict] = {
    "models": {
        "generation": "claude-opus-4-8",
        "judge": "claude-opus-4-8",
        "embedding": "local",
    },
    "injection": {
        "strategy": "B",
    },
    "budgets": {
        "max_regens": 3,
        "retrieval_top_k": 12,
    },
}


def default_root() -> Path:
    """Where all Disposition state lives (ADR 0004, fully local)."""
    return Path.home() / ".disposition"


@dataclass
class Config:
    root: Path
    models: dict
    injection: dict
    budgets: dict

    @classmethod
    def load(cls, root: Path | None = None) -> "Config":
        """Load config, falling back to defaults for anything missing."""
        root = Path(root) if root is not None else default_root()
        data = deepcopy(DEFAULT_CONFIG)
        path = root / "config.toml"
        if path.exists():
            with path.open("rb") as handle:
                loaded = tomllib.load(handle)
            for table, values in loaded.items():
                data.setdefault(table, {}).update(values)
        return cls(
            root=root,
            models=data["models"],
            injection=data["injection"],
            budgets=data["budgets"],
        )

    def write(self) -> Path:
        """Write config.toml, creating the root directory if needed."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "config.toml"
        tables = {
            "models": self.models,
            "injection": self.injection,
            "budgets": self.budgets,
        }
        path.write_text(_render_toml(tables))
        return path


def _render_toml(tables: dict[str, dict]) -> str:
    lines: list[str] = []
    for table, values in tables.items():
        lines.append(f"[{table}]")
        for key, value in values.items():
            lines.append(f"{key} = {_fmt(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _fmt(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
