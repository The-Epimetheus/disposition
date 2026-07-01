"""Tests for self-aging + Drift delta-queries, driven by FakeLLM (no network).

Aging: an old Provisional Rule decays past the floor and is dropped, a recent
Provisional Rule keeps most of its confidence, and Confirmed Rules are never
touched. Drift: `detect_drift` returns a DeltaQuery only when the fake judge
reports a contradiction against a real Confirmed key.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.aging import DeltaQuery, age_profile, detect_drift
from disposition.llm import FakeLLM
from disposition.models import Exemplar, Layer, Rule, Status
from disposition.store import Store


def _store(tmp) -> Store:
    store = Store(pathlib.Path(tmp))
    store.scaffold("java")
    return store


class TestAgeProfile(unittest.TestCase):
    def test_old_provisional_drops_recent_stays_confirmed_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            store.save_rules(
                Layer.LANGUAGE,
                [
                    # ~2 years old, provisional: 0.5 ** (~8 half-lives) << floor.
                    Rule(
                        key="stale",
                        text="old guess",
                        status=Status.PROVISIONAL,
                        layer=Layer.LANGUAGE,
                        confidence=0.6,
                        created="2024-01-01",
                    ),
                    # 10 days old, provisional: barely decays, stays.
                    Rule(
                        key="fresh",
                        text="recent guess",
                        status=Status.PROVISIONAL,
                        layer=Layer.LANGUAGE,
                        confidence=0.6,
                        created="2026-06-21",
                    ),
                    # Confirmed with an ancient date: must be left exactly as-is.
                    Rule(
                        key="settled",
                        text="the developer's word",
                        status=Status.CONFIRMED,
                        layer=Layer.LANGUAGE,
                        confidence=0.5,
                        created="2020-01-01",
                    ),
                ],
                "java",
            )

            result = age_profile(store, language="java", now="2026-07-01")
            self.assertEqual(result["dropped"], 1)
            self.assertEqual(result["aged"], 1)

            rules = {r.key: r for r in store.load_rules(Layer.LANGUAGE, "java")}
            self.assertNotIn("stale", rules)          # decayed past the floor
            self.assertIn("fresh", rules)             # still steering
            self.assertLess(rules["fresh"].confidence, 0.6)
            self.assertGreater(rules["fresh"].confidence, 0.15)
            # Confirmed rule is untouched: same confidence, still present.
            self.assertIn("settled", rules)
            self.assertEqual(rules["settled"].confidence, 0.5)
            self.assertIs(rules["settled"].status, Status.CONFIRMED)


class TestDetectDrift(unittest.TestCase):
    def test_contradiction_yields_delta_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            store.save_rules(
                Layer.LANGUAGE,
                [
                    Rule(
                        key="early-returns",
                        text="Prefer early returns over nested conditionals.",
                        status=Status.CONFIRMED,
                        layer=Layer.LANGUAGE,
                        confidence=0.9,
                        created="2025-01-01",
                    )
                ],
                "java",
            )
            store.add_exemplars(
                Layer.LANGUAGE,
                [
                    Exemplar(
                        id="e1",
                        code="if (x) { if (y) { deep(); } }",
                        language="java",
                        layer=Layer.LANGUAGE,
                        provenance="correction",
                        created="2026-06-20",
                    )
                ],
                "java",
            )

            llm = FakeLLM([
                [
                    {
                        "rule_key": "early-returns",
                        "evidence": "recent corrections nest conditionals",
                        "question": "Do you still prefer early returns?",
                    }
                ]
            ])
            queries = detect_drift(store, language="java", llm=llm, now="2026-07-01")
            self.assertEqual(len(queries), 1)
            self.assertIsInstance(queries[0], DeltaQuery)
            self.assertEqual(queries[0].rule_key, "early-returns")
            self.assertIn("early returns", queries[0].rule_text)

            # Nothing was mutated: the Confirmed rule is still there unchanged.
            rules = store.load_rules(Layer.LANGUAGE, "java")
            self.assertEqual(rules[0].confidence, 0.9)
            self.assertIs(rules[0].status, Status.CONFIRMED)

    def test_no_contradiction_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            store.save_rules(
                Layer.LANGUAGE,
                [
                    Rule(
                        key="early-returns",
                        text="Prefer early returns.",
                        status=Status.CONFIRMED,
                        layer=Layer.LANGUAGE,
                        created="2025-01-01",
                    )
                ],
                "java",
            )
            store.add_exemplars(
                Layer.LANGUAGE,
                [
                    Exemplar(
                        id="e1",
                        code="return x;",
                        language="java",
                        layer=Layer.LANGUAGE,
                        provenance="ambient",
                        created="2026-06-20",
                    )
                ],
                "java",
            )
            queries = detect_drift(
                store, language="java", llm=FakeLLM([[]]), now="2026-07-01"
            )
            self.assertEqual(queries, [])

    def test_ignores_hallucinated_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            store.save_rules(
                Layer.LANGUAGE,
                [
                    Rule(
                        key="early-returns",
                        text="Prefer early returns.",
                        status=Status.CONFIRMED,
                        layer=Layer.LANGUAGE,
                        created="2025-01-01",
                    )
                ],
                "java",
            )
            store.add_exemplars(
                Layer.LANGUAGE,
                [
                    Exemplar(
                        id="e1",
                        code="if (x) { if (y) {} }",
                        language="java",
                        layer=Layer.LANGUAGE,
                        provenance="correction",
                        created="2026-06-20",
                    )
                ],
                "java",
            )
            llm = FakeLLM([[{"rule_key": "not-a-real-key", "evidence": "x"}]])
            queries = detect_drift(store, language="java", llm=llm, now="2026-07-01")
            self.assertEqual(queries, [])


if __name__ == "__main__":
    unittest.main()
