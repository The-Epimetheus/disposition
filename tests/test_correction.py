"""Tests for correction reinforcement, driven entirely by FakeLLM (no network).

Runs standalone (`python3 tests/test_correction.py`) and under discovery.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.capture.correction import (
    classify_behavior_preserving,
    reinforce,
)
from disposition.llm import FakeLLM
from disposition.models import Layer, Status
from disposition.store import Store

AI_CODE = "String f(int x){ if(x>0){ return \"y\"; } else { return \"n\"; } }"
EDITED = "String f(int x){ if(x>0) return \"y\"; return \"n\"; }"


class TestClassify(unittest.TestCase):
    def test_high_confidence_is_preserving(self):
        fake = FakeLLM([{"preserving": True, "confidence": 0.9, "reason": "same"}])
        preserving, conf, reason = classify_behavior_preserving(AI_CODE, EDITED, fake)
        self.assertTrue(preserving)
        self.assertEqual(conf, 0.9)
        self.assertEqual(reason, "same")

    def test_low_confidence_is_excluded_even_if_claimed(self):
        # Strict default-exclude: 0.3 < threshold, so preserving is False.
        fake = FakeLLM([{"preserving": True, "confidence": 0.3, "reason": "unsure"}])
        preserving, conf, _ = classify_behavior_preserving(AI_CODE, EDITED, fake)
        self.assertFalse(preserving)
        self.assertEqual(conf, 0.3)


class TestReinforce(unittest.TestCase):
    def _store(self) -> Store:
        store = Store(pathlib.Path(self.tmp.name))
        store.scaffold("java")
        return store

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_preserving_edit_adds_exemplar_and_rule(self):
        # First json() call = classify verdict; second = taste-delta rule.
        fake = FakeLLM([
            {"preserving": True, "confidence": 0.9, "reason": "refactor only"},
            {"key": "early-returns", "text": "Prefer early returns over else."},
        ])
        store = self._store()
        result = reinforce(store, ai_code=AI_CODE, edited_code=EDITED, llm=fake)

        self.assertTrue(result.accepted)
        self.assertTrue(result.exemplar_added)
        self.assertTrue(result.rule_added)

        exemplars = store.load_exemplars(Layer.LANGUAGE, "java")
        self.assertEqual(len(exemplars), 1)
        self.assertEqual(exemplars[0].code, EDITED)
        self.assertEqual(exemplars[0].provenance, "correction")

        rules = store.load_rules(Layer.LANGUAGE, "java")
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].key, "early-returns")
        self.assertEqual(rules[0].status, Status.PROVISIONAL)
        self.assertEqual(rules[0].provenance, "correction")

    def test_behavior_changing_edit_is_rejected(self):
        # Only the classify call happens; low confidence -> excluded, no writes.
        fake = FakeLLM([{"preserving": True, "confidence": 0.3, "reason": "bug fix"}])
        store = self._store()
        result = reinforce(store, ai_code=AI_CODE, edited_code=EDITED, llm=fake)

        self.assertFalse(result.accepted)
        self.assertFalse(result.exemplar_added)
        self.assertFalse(result.rule_added)
        self.assertEqual(result.reason, "bug fix")

        self.assertEqual(store.load_exemplars(Layer.LANGUAGE, "java"), [])
        self.assertEqual(store.load_rules(Layer.LANGUAGE, "java"), [])


if __name__ == "__main__":
    unittest.main()
