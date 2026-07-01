"""Tests for the two-key Cascade merge (ADR 0002, ADR 0011).

These import only `disposition.cascade` and `disposition.models`, so they run
with the standard library alone: `python3 tests/test_cascade.py`.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.cascade import active_style
from disposition.models import Layer, Rule, Status


def rule(key, layer, status, confidence=0.5, text=None):
    return Rule(
        key=key,
        text=text or f"{key}:{layer.value}:{status.value}",
        layer=layer,
        status=status,
        confidence=confidence,
    )


class CascadeTest(unittest.TestCase):
    def test_confirmed_project_beats_confirmed_personal(self):
        personal = rule("brace-style", Layer.PERSONAL, Status.CONFIRMED)
        project = rule("brace-style", Layer.PROJECT, Status.CONFIRMED)
        winners = active_style([personal, project])
        self.assertEqual(len(winners), 1)
        self.assertIs(winners[0].layer, Layer.PROJECT)

    def test_provisional_project_does_not_beat_confirmed_personal(self):
        # Status is the FIRST key, so Confirmed wins even though Project is the
        # more specific layer. This is the ADR 0011 sanction rule.
        personal = rule("brace-style", Layer.PERSONAL, Status.CONFIRMED)
        project = rule("brace-style", Layer.PROJECT, Status.PROVISIONAL)
        winners = active_style([project, personal])
        self.assertEqual(len(winners), 1)
        self.assertIs(winners[0].layer, Layer.PERSONAL)

    def test_confirmed_beats_provisional_same_layer(self):
        a = rule("naming", Layer.PERSONAL, Status.PROVISIONAL)
        b = rule("naming", Layer.PERSONAL, Status.CONFIRMED)
        winners = active_style([a, b])
        self.assertEqual(len(winners), 1)
        self.assertIs(winners[0].status, Status.CONFIRMED)

    def test_language_beats_personal_same_status(self):
        personal = rule("imports", Layer.PERSONAL, Status.CONFIRMED)
        language = rule("imports", Layer.LANGUAGE, Status.CONFIRMED)
        winners = active_style([personal, language])
        self.assertEqual(len(winners), 1)
        self.assertIs(winners[0].layer, Layer.LANGUAGE)

    def test_confidence_breaks_same_status_and_layer(self):
        low = rule("spacing", Layer.PERSONAL, Status.CONFIRMED, confidence=0.2)
        high = rule("spacing", Layer.PERSONAL, Status.CONFIRMED, confidence=0.9)
        winners = active_style([low, high])
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].confidence, 0.9)

    def test_distinct_keys_all_survive_and_sort(self):
        rules = [
            rule("zeta", Layer.PERSONAL, Status.CONFIRMED),
            rule("alpha", Layer.LANGUAGE, Status.PROVISIONAL),
        ]
        winners = active_style(rules)
        self.assertEqual([r.key for r in winners], ["alpha", "zeta"])

    def test_empty_input(self):
        self.assertEqual(active_style([]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
