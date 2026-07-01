"""The Cascade: merge Style Profile layers into a single Active Style.

This module holds the one piece of real logic in M0, and it is deliberately
free of I/O and third-party imports so it stays trivial to test. See ADR 0002
(layers cascade) and ADR 0011 (two-key precedence: confirmation status first,
then layer specificity).
"""

from __future__ import annotations

from collections.abc import Iterable

from .models import Rule


def active_style(rules: Iterable[Rule]) -> list[Rule]:
    """Merge Rules from every layer into the winning set.

    Rules are grouped by `key`. Within each group the highest-precedence Rule
    wins, where precedence is (status, layer, confidence) in that order. Ties
    keep the first Rule seen, so the result is stable. The output is sorted by
    key for a deterministic, readable Active Style.
    """
    winners: dict[str, Rule] = {}
    for rule in rules:
        current = winners.get(rule.key)
        if current is None or rule.precedence() > current.precedence():
            winners[rule.key] = rule
    return sorted(winners.values(), key=lambda r: r.key)
