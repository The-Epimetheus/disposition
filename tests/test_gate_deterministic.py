"""Tests for the deterministic tier of the Verification Gate (ADR 0006).

The deterministic tier is pure: it must catch clear mechanical breaks with no
LLM call (so it works under FakeLLM([])), and verify() must surface its
violations combined with the LLM judge's.

Runs standalone (`python3 tests/test_gate_deterministic.py`) and under
unittest discovery.
"""

from __future__ import annotations

import pathlib
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.gate import Violation, deterministic_check, verify
from disposition.llm import FakeLLM
from disposition.models import Layer, Rule, Status


def _logging_rule():
    # A CONFIRMED, mechanical rule that names a concrete forbidden pattern.
    return Rule(
        key="no-console-logging",
        text="Never use System.out; route all logging through the logger.",
        status=Status.CONFIRMED,
        layer=Layer.PROJECT,
        tags=["mechanical"],
    )


class TestDeterministicCheck(unittest.TestCase):
    def test_clean_output_no_violations(self):
        r = SimpleNamespace(rules=[_logging_rule()], exemplars=[])
        self.assertEqual(deterministic_check("int x = 1;\nreturn x;\n", r), [])

    def test_trailing_whitespace_no_llm(self):
        r = SimpleNamespace(rules=[], exemplars=[])
        v = deterministic_check("int x = 1;   \nreturn x;\n", r)
        self.assertTrue(any(x.cite == "format:trailing-whitespace" for x in v))

    def test_system_out_flagged_by_mechanical_rule(self):
        r = SimpleNamespace(rules=[_logging_rule()], exemplars=[])
        v = deterministic_check('System.out.println("hi");\n', r)
        self.assertTrue(any(x.cite == "no-console-logging" for x in v))

    def test_system_out_not_flagged_without_rule(self):
        # No mechanical logging rule -> the deterministic tier stays quiet.
        r = SimpleNamespace(rules=[], exemplars=[])
        v = deterministic_check('System.out.println("hi");\n', r)
        self.assertFalse(any("logging" in x.cite for x in v))

    def test_final_rule_is_judgement_skipped(self):
        rule = Rule(
            key="final-locals",
            text="Prefer final for local variables.",
            status=Status.CONFIRMED,
            layer=Layer.LANGUAGE,
            tags=["mechanical"],
        )
        r = SimpleNamespace(rules=[rule], exemplars=[])
        self.assertEqual(deterministic_check("int x = 1;\n", r), [])

    def test_provisional_mechanical_rule_ignored(self):
        rule = _logging_rule()
        rule.status = Status.PROVISIONAL
        r = SimpleNamespace(rules=[rule], exemplars=[])
        v = deterministic_check('System.out.println("hi");\n', r)
        self.assertFalse(any(x.cite == "no-console-logging" for x in v))


class TestVerifyCombines(unittest.TestCase):
    def test_deterministic_caught_with_fake_llm_empty(self):
        # Judge finds nothing ([]) but the deterministic tier catches the print.
        r = SimpleNamespace(rules=[_logging_rule()], exemplars=[])
        result = verify('System.out.println("x");   \n', r, llm=FakeLLM([[]]))
        self.assertFalse(result.passed)
        self.assertTrue(result.escalated)
        cites = {v.cite for v in result.violations}
        self.assertIn("no-console-logging", cites)
        self.assertIn("format:trailing-whitespace", cites)

    def test_deterministic_and_judge_violations_combined(self):
        # Judge reports one violation; deterministic tier adds another.
        r = SimpleNamespace(rules=[_logging_rule()], exemplars=[])
        llm = FakeLLM([[{"cite": "early-returns", "detail": "nested if/else"}]])
        result = verify('System.out.println("x");\n', r, llm=llm)
        cites = {v.cite for v in result.violations}
        self.assertIn("early-returns", cites)       # from the judge
        self.assertIn("no-console-logging", cites)  # from the deterministic tier

    def test_regenerate_clears_both_tiers(self):
        # Round 1: deterministic print + judge violation. Regenerate returns
        # clean code; round 2 both tiers pass.
        r = SimpleNamespace(rules=[_logging_rule()], exemplars=[])
        llm = FakeLLM([
            [{"cite": "early-returns", "detail": "nested"}],
            [],
        ])
        result = verify(
            'System.out.println("x");\n', r, llm=llm,
            regenerate=lambda prev, vs: "logger.info(\"x\");\n",
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.regens, 1)
        self.assertEqual(result.violations, [])


if __name__ == "__main__":
    unittest.main()
