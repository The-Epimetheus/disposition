"""Tests for the Forced Injection strategies (ADR 0003 / Q19).

Seeds a Store with several Confirmed rules (plus one Provisional) and three
LANGUAGE exemplars with a persisted index, then checks each policy:
  A  -> all Confirmed rules + all exemplars (task-independent).
  B  -> task-scoped subset of exemplars (delegates to retrieval).
  C  -> all Confirmed rules but only the task-relevant exemplars.
Offline LocalEmbedder only; no network.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.embeddings import LocalEmbedder
from disposition.index import VectorIndex
from disposition.injection import Injection, build_injection
from disposition.models import Exemplar, Layer, Rule, Status
from disposition.store import Store


RETRY_CODE = (
    "int retryWithBackoff(Supplier<Integer> op) {\n"
    "    for (int attempt = 0; attempt < maxRetries; attempt++) {\n"
    "        try { return op.get(); } catch (IOException e) { sleep(backoff); }\n"
    "    }\n"
    "    throw new RetryExhaustedException();\n"
    "}"
)
PARSE_CODE = (
    "LocalDate parseDate(String raw) {\n"
    "    return LocalDate.parse(raw, DateTimeFormatter.ISO_DATE);\n"
    "}"
)
STREAM_CODE = (
    "List<String> names(List<User> users) {\n"
    "    return users.stream().map(User::getName).collect(toList());\n"
    "}"
)


class InjectionTest(unittest.TestCase):
    def _store(self, tmp: str) -> Store:
        store = Store(pathlib.Path(tmp))
        store.scaffold("java")

        exemplars = [
            Exemplar(id=Exemplar.make_id("Retry.java", 10, RETRY_CODE), code=RETRY_CODE,
                     language="java", layer=Layer.LANGUAGE, source="Retry.java"),
            Exemplar(id=Exemplar.make_id("Parse.java", 3, PARSE_CODE), code=PARSE_CODE,
                     language="java", layer=Layer.LANGUAGE, source="Parse.java"),
            Exemplar(id=Exemplar.make_id("Stream.java", 5, STREAM_CODE), code=STREAM_CODE,
                     language="java", layer=Layer.LANGUAGE, source="Stream.java"),
        ]
        store.add_exemplars(Layer.LANGUAGE, exemplars, "java")

        store.save_rules(
            Layer.PERSONAL,
            [Rule(key="early-returns", text="Prefer early returns.",
                  status=Status.CONFIRMED, layer=Layer.PERSONAL, confidence=0.9)],
        )
        store.save_rules(
            Layer.LANGUAGE,
            [
                Rule(key="retries", text="Use exponential backoff for retries.",
                     status=Status.CONFIRMED, layer=Layer.LANGUAGE, confidence=0.8),
                Rule(key="dates", text="Parse dates with DateTimeFormatter.",
                     status=Status.CONFIRMED, layer=Layer.LANGUAGE, confidence=0.7),
                Rule(key="streams", text="Favor streams for collection mapping.",
                     status=Status.PROVISIONAL, layer=Layer.LANGUAGE, confidence=0.4),
            ],
            "java",
        )

        embedder = LocalEmbedder()
        vectors = embedder.embed([ex.code for ex in exemplars])
        index = VectorIndex(embedder.dim)
        index.add_many(
            [(ex.id, vectors[i], {"source": ex.source}) for i, ex in enumerate(exemplars)]
        )
        index.save(store.index_dir(Layer.LANGUAGE, "java"))
        return store

    def test_strategy_a_returns_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            got = build_injection(store, language="java", strategy="A",
                                  embedder=LocalEmbedder())
            self.assertIsInstance(got, Injection)
            # Only Confirmed rules ship; the Provisional "streams" is dropped.
            self.assertEqual({r.key for r in got.rules},
                             {"early-returns", "retries", "dates"})
            # All three exemplars, regardless of task.
            self.assertEqual({ex.source for ex in got.exemplars},
                             {"Retry.java", "Parse.java", "Stream.java"})

    def test_strategy_b_scopes_exemplars_to_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            got = build_injection(
                store, language="java", strategy="B", k_exemplars=1,
                task="add retry with exponential backoff on IOException",
                embedder=LocalEmbedder(),
            )
            # A task-scoped subset: the single nearest exemplar is the retry one.
            self.assertEqual(len(got.exemplars), 1)
            self.assertEqual(got.exemplars[0].source, "Retry.java")
            # B mirrors retrieval, so the Provisional rule is present.
            self.assertIn("streams", {r.key for r in got.rules})

    def test_strategy_c_full_rules_scoped_exemplars(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            got = build_injection(
                store, language="java", strategy="C", k_exemplars=1,
                task="map users to their names with a stream",
                embedder=LocalEmbedder(),
            )
            # All Confirmed rules (no Provisional), like strategy A.
            self.assertEqual({r.key for r in got.rules},
                             {"early-returns", "retries", "dates"})
            # But exemplars are scoped to the task, like strategy B.
            self.assertEqual(len(got.exemplars), 1)
            self.assertEqual(got.exemplars[0].source, "Stream.java")

    def test_unknown_strategy_falls_back_to_b(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            unknown = build_injection(
                store, language="java", strategy="ZZZ", k_exemplars=2,
                task="parse a date string", embedder=LocalEmbedder(),
            )
            dynamic = build_injection(
                store, language="java", strategy="B", k_exemplars=2,
                task="parse a date string", embedder=LocalEmbedder(),
            )
            self.assertEqual({r.key for r in unknown.rules},
                             {r.key for r in dynamic.rules})
            self.assertEqual([ex.source for ex in unknown.exemplars],
                             [ex.source for ex in dynamic.exemplars])


if __name__ == "__main__":
    unittest.main(verbosity=2)
