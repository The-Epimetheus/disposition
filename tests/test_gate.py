"""Tests for the Verification Gate, driven entirely by FakeLLM (no network).

Covers the three loop outcomes: clean on first pass, clean after a regenerate
callback fixes the violations, and escalation when violations persist to the cap.

Runs standalone (`python3 tests/test_gate.py`) and under unittest discovery.
"""

from __future__ import annotations

import pathlib
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.gate import GateResult, Violation, judge, llm_regenerator, verify
from disposition.llm import FakeLLM
from disposition.models import Layer, Rule, Status


def _retrieved():
    # A minimal stand-in for retrieval.Retrieved: just needs .rules/.exemplars.
    rule = Rule(
        key="early-returns",
        text="Prefer early returns over nested conditionals.",
        status=Status.CONFIRMED,
        layer=Layer.LANGUAGE,
    )
    return SimpleNamespace(rules=[rule], exemplars=[])


class TestJudge(unittest.TestCase):
    def test_empty_list_means_no_violations(self):
        v = judge("code", _retrieved(), FakeLLM([[]]))
        self.assertEqual(v, [])

    def test_parses_violation_objects(self):
        payload = [{"cite": "early-returns", "detail": "nested if/else"}]
        v = judge("code", _retrieved(), FakeLLM([payload]))
        self.assertEqual(len(v), 1)
        self.assertIsInstance(v[0], Violation)
        self.assertEqual(v[0].cite, "early-returns")

    def test_accepts_wrapped_violations_shape(self):
        payload = {"violations": [{"cite": "k", "detail": "d"}]}
        v = judge("code", _retrieved(), FakeLLM([payload]))
        self.assertEqual(v[0].cite, "k")


class TestVerify(unittest.TestCase):
    def test_a_clean_first_pass(self):
        result = verify("good code", _retrieved(), llm=FakeLLM([[]]))
        self.assertIsInstance(result, GateResult)
        self.assertTrue(result.passed)
        self.assertEqual(result.regens, 0)
        self.assertFalse(result.escalated)
        self.assertEqual(result.final_output, "good code")

    def test_b_regenerate_fixes_after_violations(self):
        # First judge finds a violation; after regenerate, second judge is clean.
        llm = FakeLLM([
            [{"cite": "early-returns", "detail": "nested if/else"}],
            [],
        ])
        calls = {"n": 0}

        def regenerate(prev, violations):
            calls["n"] += 1
            # The callback receives the offending output and its violations.
            self.assertIn("early-returns", violations[0].cite)
            return "fixed code"

        result = verify("bad code", _retrieved(), llm=llm, regenerate=regenerate)
        self.assertTrue(result.passed)
        self.assertEqual(result.regens, 1)
        self.assertFalse(result.escalated)
        self.assertEqual(result.final_output, "fixed code")
        self.assertEqual(calls["n"], 1)

    def test_c_persistent_violations_escalate_at_cap(self):
        # Judge always reports a violation; regenerate never satisfies it.
        def script(prompt, kind):
            return [{"cite": "early-returns", "detail": "still nested"}]

        result = verify(
            "bad code",
            _retrieved(),
            llm=FakeLLM(script),
            max_regens=2,
            regenerate=lambda prev, violations: "still bad",
        )
        self.assertFalse(result.passed)
        self.assertTrue(result.escalated)
        self.assertEqual(result.regens, 2)
        self.assertEqual(len(result.violations), 1)

    def test_violations_but_no_regenerate_callback(self):
        # Without a callback there is nothing to retry; escalate immediately.
        llm = FakeLLM([[{"cite": "k", "detail": "d"}]])
        result = verify("bad", _retrieved(), llm=llm)
        self.assertFalse(result.passed)
        self.assertTrue(result.escalated)
        self.assertEqual(result.regens, 0)


class TestLlmRegenerator(unittest.TestCase):
    def test_retry_is_anchored_to_rules_and_violations(self):
        seen = {}

        def script(prompt, kind):
            seen["prompt"] = prompt
            return "rewritten code"

        regen = llm_regenerator(FakeLLM(script), _retrieved(), task="add()")
        out = regen("bad code", [Violation("early-returns", "nested if/else")])

        self.assertEqual(out, "rewritten code")
        # The retry prompt must carry the rules, the citation, and the attempt.
        self.assertIn("early-returns", seen["prompt"])
        self.assertIn("nested if/else", seen["prompt"])
        self.assertIn("bad code", seen["prompt"])
        self.assertIn("add()", seen["prompt"])

    def test_the_full_loop_with_the_regenerator(self):
        # verify + llm_regenerator: first judge flags, regen rewrites via
        # complete(), second judge passes. One FakeLLM drives both roles.
        def script(prompt, kind):
            if kind == "complete":
                return "clean code"
            return [] if "clean code" in prompt else [{"cite": "k", "detail": "d"}]

        llm = FakeLLM(script)
        result = verify(
            "bad code",
            _retrieved(),
            llm=llm,
            regenerate=llm_regenerator(llm, _retrieved()),
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.regens, 1)
        self.assertEqual(result.final_output, "clean code")


if __name__ == "__main__":
    unittest.main()
