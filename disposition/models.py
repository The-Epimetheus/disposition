"""Core data types for a Style Profile.

A Rule is the legible, editable unit of style (see CONTEXT.md). Every Rule
carries a confirmation status and belongs to a Cascade layer. Those two facts
drive the two-key precedence used to merge layers into an Active Style; see
`cascade.py` and ADR 0002 / ADR 0011.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    """Whether a Rule actively steers generation yet."""

    CONFIRMED = "confirmed"
    PROVISIONAL = "provisional"


class Layer(str, Enum):
    """Which scope a Rule belongs to. More specific layers sit higher."""

    PERSONAL = "personal"
    LANGUAGE = "language"
    PROJECT = "project"


# First precedence key: a Confirmed Rule outranks a Provisional one.
STATUS_RANK: dict[Status, int] = {
    Status.PROVISIONAL: 0,
    Status.CONFIRMED: 1,
}

# Second precedence key: Project beats Language beats Personal.
LAYER_RANK: dict[Layer, int] = {
    Layer.PERSONAL: 1,
    Layer.LANGUAGE: 2,
    Layer.PROJECT: 3,
}


@dataclass
class Rule:
    """A distilled, plain-language statement of one style preference.

    `key` names the topic the Rule addresses (for example "error-handling" or
    "early-returns"). Two Rules with the same `key` conflict, and the Cascade
    keeps the winner. Rules with distinct keys all coexist in the Active Style.
    """

    key: str
    text: str
    status: Status
    layer: Layer
    confidence: float = 0.5
    provenance: str = ""
    tags: list[str] = field(default_factory=list)

    def precedence(self) -> tuple[int, int, float]:
        """The two-key precedence, with confidence as a same-layer tiebreaker.

        Order matters: status first, then layer, then confidence. That is why a
        Provisional Project Rule does not beat a Confirmed Personal Rule, even
        though Project is the more specific layer (ADR 0011).
        """
        return (STATUS_RANK[self.status], LAYER_RANK[self.layer], self.confidence)


@dataclass
class Exemplar:
    """A snippet of the developer's real code, retrieved as a few-shot example.

    Exemplars carry the tacit texture of Style that Rules cannot put into words
    (see CONTEXT.md). `id` is stable and content-derived so re-ingesting the same
    span does not create duplicates. Exemplars are embedded and indexed for
    retrieval; the index is a derived cache, rebuildable from these records.
    """

    id: str
    code: str
    language: str
    layer: Layer
    source: str = ""            # file path, or "interview:<scenario>" etc.
    start_line: int = 0
    end_line: int = 0
    provenance: str = ""        # "bootstrap" | "interview" | "correction"
    tags: list[str] = field(default_factory=list)

    @staticmethod
    def make_id(source: str, start_line: int, code: str) -> str:
        """A stable id from where the snippet came and what it contains."""
        digest = hashlib.sha1(
            f"{source}:{start_line}:{code}".encode("utf-8")
        ).hexdigest()
        return digest[:16]
