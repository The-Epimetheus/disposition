"""Tests for Rule induction and triage, driven entirely by FakeLLM (no network).

Runs standalone (`python3 tests/test_induction.py`) and under unittest discovery.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.induction import Candidate, induce, triage
from disposition.llm import FakeLLM
from disposition.models import Exemplar, Layer, Status
from disposition.store import Store


def _store() -> Store:
    tmp = tempfile.mkdtemp()
    store = Store(pathlib.Path(tmp))
    store.scaffold("java")
    return store


def _seed_exemplars(store: Store) -> None:
    store.add_exemplars(
        Layer.LANGUAGE,
        [
            Exemplar(
                id=Exemplar.make_id("A.java", 1, "int x = 1;"),
                code="int x = 1;",
                language="java",
                layer=Layer.LANGUAGE,
                provenance="bootstrap",
            )
        ],
        language="java",
    )


# Canned candidate rules: one mechanical+high-confidence, one mechanical but
# low-confidence, and one non-mechanical (a judgement call).
_CANNED = [
    {
        "key": "brace-style",
        "text": "Opening braces go on the same line.",
        "confidence": 0.95,
        "mechanical": True,
    },
    {
        "key": "field-casing",
        "text": "Prefer camelCase field names.",
        "confidence": 0.5,
        "mechanical": True,
    },
    {
        "key": "early-return",
        "text": "Guard clauses with early returns over nested conditionals.",
        "confidence": 0.8,
        "mechanical": False,
    },
]


class TestInduce(unittest.TestCase):
    def test_empty_store_skips_llm(self):
        store = _store()
        # No exemplars -> induce short-circuits and never calls the (empty) fake.
        self.assertEqual(induce(store, language="java", llm=FakeLLM([])), [])

    def test_parses_candidates(self):
        store = _store()
        _seed_exemplars(store)
        cands = induce(store, language="java", llm=FakeLLM([list(_CANNED)]))
        self.assertEqual([c.key for c in cands], [c["key"] for c in _CANNED])
        self.assertTrue(cands[0].mechanical)
        self.assertFalse(cands[2].mechanical)

    def test_accepts_wrapped_object_and_skips_malformed(self):
        store = _store()
        _seed_exemplars(store)
        payload = {"candidates": [{"key": "k", "text": "t"}, {"nope": 1}]}
        cands = induce(store, language="java", llm=FakeLLM([payload]))
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].key, "k")


class TestTriageAuto(unittest.TestCase):
    def test_auto_confirms_mechanical_leaves_others_provisional(self):
        store = _store()
        cands = [
            Candidate(**c) for c in _CANNED  # type: ignore[arg-type]
        ]
        result = triage(store, cands, language="java", auto=True)

        self.assertEqual(result, {"confirmed": 1, "provisional": 2})

        rules = {r.key: r for r in store.load_rules(Layer.LANGUAGE, "java")}
        self.assertEqual(rules["brace-style"].status, Status.CONFIRMED)
        # Mechanical but low-confidence stays Provisional.
        self.assertEqual(rules["field-casing"].status, Status.PROVISIONAL)
        # Non-mechanical is never auto-confirmed.
        self.assertEqual(rules["early-return"].status, Status.PROVISIONAL)
        self.assertEqual(rules["brace-style"].provenance, "induction")

    def test_merge_replaces_same_key(self):
        store = _store()
        triage(
            store,
            [Candidate("brace-style", "old", 0.9, True)],
            language="java",
            auto=True,
        )
        triage(
            store,
            [Candidate("brace-style", "new", 0.9, True)],
            language="java",
            auto=True,
        )
        rules = store.load_rules(Layer.LANGUAGE, "java")
        matching = [r for r in rules if r.key == "brace-style"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].text, "new")


class TestTriageInteractive(unittest.TestCase):
    def test_choices_map_to_status(self):
        store = _store()
        cands = [
            Candidate("a", "ta", 0.5, False),
            Candidate("b", "tb", 0.5, False),
            Candidate("c", "tc", 0.5, False),
        ]
        # confirm a, reject b, default (empty) -> provisional for c.
        answers = iter(["c", "r", ""])
        result = triage(
            store,
            cands,
            language="java",
            auto=False,
            input_fn=lambda _prompt: next(answers),
            output_fn=lambda *_a, **_k: None,
        )
        self.assertEqual(result, {"confirmed": 1, "provisional": 1})
        rules = {r.key: r.status for r in store.load_rules(Layer.LANGUAGE, "java")}
        self.assertEqual(rules, {"a": Status.CONFIRMED, "c": Status.PROVISIONAL})


if __name__ == "__main__":
    unittest.main()
