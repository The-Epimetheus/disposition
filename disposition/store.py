"""Persist Rules on disk and compute the Active Style.

The store owns the ~/.disposition/profiles/ tree. Rules live in a legible,
hand-editable rules.yaml per layer (the trust mechanism, ADR 0008). The
Personal layer is a fixed directory; the Language layer is named for the
language itself (for example profiles/java). The Project layer is phase 2.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .cascade import active_style
from .models import Exemplar, Layer, Rule, Status


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.profiles = self.root / "profiles"

    # -- paths ---------------------------------------------------------------

    def _layer_dir(self, layer: Layer, language: str | None = None) -> Path:
        if layer is Layer.PERSONAL:
            return self.profiles / "personal"
        if layer is Layer.LANGUAGE:
            if not language:
                raise ValueError("the Language layer needs a language name")
            return self.profiles / language
        if layer is Layer.PROJECT:
            return self.profiles / "project"
        raise ValueError(f"unknown layer: {layer!r}")

    # -- reading -------------------------------------------------------------

    def load_rules(self, layer: Layer, language: str | None = None) -> list[Rule]:
        path = self._layer_dir(layer, language) / "rules.yaml"
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        rules: list[Rule] = []
        for item in data.get("rules", []):
            rules.append(
                Rule(
                    key=item["key"],
                    text=item["text"],
                    # The layer is set by the directory, not by the file, so a
                    # file can never claim a layer it does not live in.
                    layer=layer,
                    status=Status(item.get("status", "provisional")),
                    confidence=float(item.get("confidence", 0.5)),
                    provenance=item.get("provenance", ""),
                    tags=list(item.get("tags", [])),
                )
            )
        return rules

    def load_active_layers(self, language: str) -> list[Rule]:
        """All Rules from the layers active in v1 (Personal + Language)."""
        rules = self.load_rules(Layer.PERSONAL)
        rules += self.load_rules(Layer.LANGUAGE, language)
        # Project layer is phase 2 (ADR 0011); nothing to merge in v1.
        return rules

    def active_style(self, language: str) -> list[Rule]:
        """The merged, winning set of Rules for a given language."""
        return active_style(self.load_active_layers(language))

    # -- exemplars -----------------------------------------------------------

    def exemplars_dir(self, layer: Layer, language: str | None = None) -> Path:
        return self._layer_dir(layer, language) / "exemplars"

    def index_dir(self, layer: Layer, language: str | None = None) -> Path:
        return self._layer_dir(layer, language) / "index"

    def load_exemplars(
        self, layer: Layer, language: str | None = None
    ) -> list[Exemplar]:
        path = self.exemplars_dir(layer, language) / "exemplars.yaml"
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        exemplars: list[Exemplar] = []
        for item in data.get("exemplars", []):
            exemplars.append(
                Exemplar(
                    id=item["id"],
                    code=item["code"],
                    language=item.get("language", language or ""),
                    layer=layer,
                    source=item.get("source", ""),
                    start_line=int(item.get("start_line", 0)),
                    end_line=int(item.get("end_line", 0)),
                    provenance=item.get("provenance", ""),
                    tags=list(item.get("tags", [])),
                )
            )
        return exemplars

    def save_exemplars(
        self, layer: Layer, exemplars: list[Exemplar], language: str | None = None
    ) -> Path:
        directory = self.exemplars_dir(layer, language)
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "exemplars": [
                {
                    "id": ex.id,
                    "code": ex.code,
                    "language": ex.language,
                    "source": ex.source,
                    "start_line": ex.start_line,
                    "end_line": ex.end_line,
                    "provenance": ex.provenance,
                    "tags": ex.tags,
                }
                for ex in exemplars
            ]
        }
        path = directory / "exemplars.yaml"
        path.write_text(yaml.safe_dump(payload, sort_keys=False))
        return path

    def add_exemplars(
        self, layer: Layer, new: list[Exemplar], language: str | None = None
    ) -> list[Exemplar]:
        """Append exemplars, de-duplicating by id. Returns the merged set."""
        existing = self.load_exemplars(layer, language)
        by_id = {ex.id: ex for ex in existing}
        for ex in new:
            by_id[ex.id] = ex
        merged = list(by_id.values())
        self.save_exemplars(layer, merged, language)
        return merged

    def all_exemplars(self, language: str) -> list[Exemplar]:
        """Exemplars from the layers active in v1 (Personal + Language)."""
        return self.load_exemplars(Layer.PERSONAL) + self.load_exemplars(
            Layer.LANGUAGE, language
        )

    # -- writing -------------------------------------------------------------

    def save_rules(
        self, layer: Layer, rules: list[Rule], language: str | None = None
    ) -> Path:
        directory = self._layer_dir(layer, language)
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "rules": [
                {
                    "key": rule.key,
                    "text": rule.text,
                    "status": rule.status.value,
                    "confidence": rule.confidence,
                    "provenance": rule.provenance,
                    "tags": rule.tags,
                }
                for rule in rules
            ]
        }
        path = directory / "rules.yaml"
        path.write_text(yaml.safe_dump(payload, sort_keys=False))
        return path

    def scaffold(self, language: str) -> None:
        """Create the on-disk profile tree for the active layers."""
        for directory in (
            self._layer_dir(Layer.PERSONAL),
            self._layer_dir(Layer.LANGUAGE, language),
        ):
            (directory / "exemplars").mkdir(parents=True, exist_ok=True)
            (directory / "index").mkdir(parents=True, exist_ok=True)
            rules_path = directory / "rules.yaml"
            if not rules_path.exists():
                rules_path.write_text("rules: []\n")
        (self.root / "provenance").mkdir(parents=True, exist_ok=True)
        (self.root / "interview").mkdir(parents=True, exist_ok=True)
