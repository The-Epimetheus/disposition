"""Tests for the provocation interview (disposition.capture.interview).

Runs non-interactively from the canned transcript fixture (the completed HITL
step): "declare" answers must land as Confirmed Rules, "do" answers as
Provisional Rules plus retrievable Exemplars. No network, no anthropic, no
tree-sitter; only stdlib + disposition + the offline LocalEmbedder.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.capture.interview import (
    SCENARIOS,
    InterviewResult,
    load_transcript,
    run_interview,
)
from disposition.index import VectorIndex
from disposition.models import Layer, Status
from disposition.store import Store

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "interview_transcript.yaml"


class InterviewTranscriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.tmp.name))
        self.store.scaffold("java")
        self.transcript = load_transcript(FIXTURE)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scenarios_are_three_and_non_leading(self):
        self.assertEqual(len(SCENARIOS), 3)
        for s in SCENARIOS:
            self.assertIn("id", s)
            self.assertIn("key", s)
            self.assertTrue(s["prompt"] and s["java_snippet"])

    def test_transcript_fixture_has_all_scenarios(self):
        ids = {a["scenario"] for a in self.transcript["answers"]}
        self.assertEqual(ids, {s["id"] for s in SCENARIOS})

    def test_run_adds_rules_and_exemplars(self):
        result = run_interview(self.store, language="java", transcript=self.transcript)
        self.assertIsInstance(result, InterviewResult)
        # Fixture: two "do" answers (2 exemplars) + three rules total.
        self.assertEqual(result.exemplars_added, 2)
        self.assertEqual(result.rules_added, 3)

    def test_declare_is_confirmed_and_do_is_provisional(self):
        run_interview(self.store, language="java", transcript=self.transcript)
        rules = {r.key: r for r in self.store.load_rules(Layer.LANGUAGE, "java")}
        # "nested-cleanup" was a declare -> Confirmed.
        self.assertEqual(rules["control-flow"].status, Status.CONFIRMED)
        self.assertEqual(rules["control-flow"].provenance, "interview:declared")
        # "data-race" and "resource-leak" were do -> Provisional.
        self.assertEqual(rules["thread-safety"].status, Status.PROVISIONAL)
        self.assertEqual(rules["resource-management"].status, Status.PROVISIONAL)

    def test_exemplars_persisted_with_interview_provenance(self):
        run_interview(self.store, language="java", transcript=self.transcript)
        exemplars = self.store.load_exemplars(Layer.LANGUAGE, "java")
        self.assertEqual(len(exemplars), 2)
        self.assertTrue(all(ex.provenance == "interview" for ex in exemplars))
        self.assertTrue(any("AtomicInteger" in ex.code for ex in exemplars))
        self.assertTrue(any("try (InputStream" in ex.code for ex in exemplars))

    def test_index_is_built_and_loadable(self):
        run_interview(self.store, language="java", transcript=self.transcript)
        index_dir = self.store.index_dir(Layer.LANGUAGE, "java")
        self.assertTrue(VectorIndex.exists(index_dir))
        index = VectorIndex.load(index_dir)
        self.assertEqual(len(index), 2)

    def test_rerun_is_idempotent_on_exemplars(self):
        run_interview(self.store, language="java", transcript=load_transcript(FIXTURE))
        second = run_interview(self.store, language="java", transcript=load_transcript(FIXTURE))
        # Same content re-ingested: exemplar ids are stable, so nothing new adds.
        self.assertEqual(second.exemplars_added, 0)
        self.assertEqual(len(self.store.load_exemplars(Layer.LANGUAGE, "java")), 2)

    def test_voice_narration_yields_confirmed_rules(self):
        from disposition.llm import FakeLLM

        # An answer carrying /voice narration; the fake extractor names two
        # declared principles, which must land as Confirmed voice Rules.
        transcript = {
            "language": "java",
            "answers": [
                {
                    "scenario": "data-race",
                    "narration": (
                        "I always kill shared mutable state rather than lock, "
                        "and I reach for atomics when I must share."
                    ),
                }
            ],
        }
        principles = [
            {"key": "thread-safety", "text": "Prefer immutability over locks."},
            {"key": "atomics", "text": "Use atomics for shared counters."},
        ]
        result = run_interview(
            self.store,
            language="java",
            transcript=transcript,
            llm=FakeLLM([principles]),
        )
        self.assertEqual(result.rules_added, 2)
        rules = {r.key: r for r in self.store.load_rules(Layer.LANGUAGE, "java")}
        self.assertEqual(rules["thread-safety"].status, Status.CONFIRMED)
        self.assertEqual(rules["thread-safety"].provenance, "interview:voice")
        # The raw narration is saved for the record.
        transcript_file = pathlib.Path(self.tmp.name) / "interview" / "data-race.md"
        self.assertTrue(transcript_file.exists())
        self.assertIn("shared mutable state", transcript_file.read_text())

    def test_interactive_path_via_injected_io(self):
        scripted = iter(
            [
                "android",          # platform
                "",                 # language (accept default)
                "c", "Guard clauses only.",         # data-race: declare
                "d", "class X {}", ".",             # nested-cleanup: do
                "c", "Use try-with-resources.",     # resource-leak: declare
            ]
        )
        result = run_interview(
            self.store,
            language="java",
            input_fn=lambda _="": next(scripted),
            output_fn=lambda *a, **k: None,
        )
        self.assertEqual(result.exemplars_added, 1)
        self.assertEqual(result.rules_added, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
