"""Layered behavior-preservation classifier tiers (ADR 0007, issue #11)."""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import unittest

from disposition.capture.correction import (
    _structurally_equivalent,
    classify_behavior_preserving,
    run_tests,
)
from disposition.llm import FakeLLM


class StaticTierTests(unittest.TestCase):
    def test_comment_only_edit_accepted_without_llm(self):
        # FakeLLM([]) raises if json() is ever called -> proves LLM was skipped.
        ai = "int x = f(a); // old note\nreturn x;"
        edited = "int x = f(a); // brand new comment\nreturn x;"
        preserving, conf, reason = classify_behavior_preserving(
            ai, edited, FakeLLM([])
        )
        self.assertTrue(preserving)
        self.assertEqual(conf, 1.0)
        self.assertIn("formatting-only", reason)

    def test_whitespace_only_edit_accepted_without_llm(self):
        ai = "if (a) { return b; }"
        edited = "if (a) {\n    return b;\n}"
        preserving, conf, reason = classify_behavior_preserving(
            ai, edited, FakeLLM([])
        )
        self.assertTrue(preserving)
        self.assertEqual(conf, 1.0)

    def test_block_comment_stripped(self):
        self.assertTrue(
            _structurally_equivalent("a=1; /* hi */ b=2;", "a=1;   b=2;")
        )
        self.assertFalse(_structurally_equivalent("a=1;", "a=2;"))


class LlmTierTests(unittest.TestCase):
    def test_semantic_edit_routes_to_llm(self):
        # Structurally different -> falls through to the (fake) LLM classifier.
        ai = "return a + b;"
        edited = "return a - b;"
        verdict = {"preserving": False, "confidence": 0.9, "reason": "sign flip"}
        preserving, conf, reason = classify_behavior_preserving(
            ai, edited, FakeLLM([verdict])
        )
        self.assertFalse(preserving)
        self.assertEqual(reason, "sign flip")

    def test_semantic_preserving_edit_uses_llm_verdict(self):
        ai = "int total = a + b;\nreturn total;"
        edited = "final int sum = a + b;\nreturn sum;"
        verdict = {"preserving": True, "confidence": 0.95, "reason": "rename"}
        preserving, conf, reason = classify_behavior_preserving(
            ai, edited, FakeLLM([verdict])
        )
        self.assertTrue(preserving)
        self.assertEqual(conf, 0.95)


class TestHookTests(unittest.TestCase):
    def test_run_tests_none_without_command(self):
        self.assertIsNone(run_tests("/tmp", None))
        self.assertIsNone(run_tests(None, "true"))

    def test_passing_tests_accept_without_llm(self):
        ai = "return a + b;"
        edited = "return b + a;"  # not structurally equal
        preserving, conf, reason = classify_behavior_preserving(
            ai, edited, FakeLLM([]), tests_cmd="true", repo="/tmp"
        )
        self.assertTrue(preserving)
        self.assertIn("test suite passes", reason)

    def test_failing_tests_fall_through_to_llm(self):
        ai = "return a + b;"
        edited = "return b + a;"
        verdict = {"preserving": True, "confidence": 0.8, "reason": "commutative"}
        preserving, conf, reason = classify_behavior_preserving(
            ai, edited, FakeLLM([verdict]), tests_cmd="false", repo="/tmp"
        )
        self.assertTrue(preserving)
        self.assertEqual(reason, "commutative")


if __name__ == "__main__":
    unittest.main()
