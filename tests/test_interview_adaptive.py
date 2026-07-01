"""Tests for the ADAPTIVE gap-model of the interview (ADR 0012).

`adaptive_followups` must model KNOWN vs NEEDED from the seeded profile and let
the (Fake) LLM propose targeted follow-ups. `run_interview(adaptive=True)` must,
when driven live via `input_fn`/`output_fn`, capture a declared follow-up answer
as a Confirmed Rule (provenance "interview:adaptive") -- without disturbing the
fixed-battery behaviour. No network, no anthropic; stdlib + FakeLLM only.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.capture.interview import adaptive_followups, run_interview
from disposition.llm import FakeLLM
from disposition.models import Layer, Rule, Status
from disposition.store import Store


def _seed(store):
    """Seed one known rule so the gap-model has a 'KNOWN' to reason against."""
    store.save_rules(
        Layer.LANGUAGE,
        [
            Rule(
                key="thread-safety",
                text="Use atomics for shared counters.",
                status=Status.CONFIRMED,
                layer=Layer.LANGUAGE,
                confidence=0.9,
                provenance="seed",
            )
        ],
        "java",
    )


class AdaptiveFollowupsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.tmp.name))
        self.store.scaffold("java")
        _seed(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_targeted_questions_from_profile(self):
        llm = FakeLLM(
            [
                [
                    {"key": "naming", "question": "How do you name package-private helpers?"},
                    {"key": "error-handling", "question": "What do you do with checked exceptions?"},
                    {"key": "", "question": "dropped: no key"},
                ]
            ]
        )
        out = adaptive_followups(self.store, language="java", llm=llm, max_questions=3)
        self.assertEqual([q["key"] for q in out], ["naming", "error-handling"])
        self.assertTrue(all(q["question"] for q in out))

    def test_respects_max_questions(self):
        llm = FakeLLM(
            [[{"key": f"k{i}", "question": f"q{i}?"} for i in range(5)]]
        )
        out = adaptive_followups(self.store, language="java", llm=llm, max_questions=2)
        self.assertEqual(len(out), 2)


class AdaptiveRunInterviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.tmp.name))
        self.store.scaffold("java")
        _seed(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_adaptive_answer_becomes_confirmed_rule(self):
        # Script the whole live run: platform, language, three declared fixed
        # scenarios, then one declared adaptive follow-up answer.
        inputs = iter(
            [
                "backend",  # platform
                "",  # language [java]
                "c", "Declare threads via Atomic.",  # data-race (declare)
                "c", "Use guard clauses.",  # nested-cleanup (declare)
                "c", "Use try-with-resources.",  # resource-leak (declare)
                "Prefer descriptive names.",  # adaptive follow-up answer
            ]
        )
        llm = FakeLLM(
            [[{"key": "naming", "question": "How do you name things?"}]]
        )
        run_interview(
            self.store,
            language="java",
            adaptive=True,
            llm=llm,
            input_fn=lambda *_a, **_k: next(inputs),
            output_fn=lambda *_a, **_k: None,
        )
        rules = {r.key: r for r in self.store.load_rules(Layer.LANGUAGE, "java")}
        self.assertIn("naming", rules)
        self.assertEqual(rules["naming"].status, Status.CONFIRMED)
        self.assertEqual(rules["naming"].provenance, "interview:adaptive")
        self.assertEqual(rules["naming"].text, "Prefer descriptive names.")
        # Fixed battery still landed alongside the adaptive rule.
        self.assertEqual(rules["control-flow"].provenance, "interview:declared")


if __name__ == "__main__":
    unittest.main()
