"""Tests for the retrieval read-side (ADR 0006/0007).

Seeds a Store with LANGUAGE exemplars + rules, builds a persisted index with
the offline LocalEmbedder, and checks that retrieve() ranks the relevant
exemplar first and returns the merged Active Style. Also covers the on-the-fly
index rebuild path and the Confirmed-rule violation filter. No network.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.embeddings import LocalEmbedder
from disposition.index import VectorIndex
from disposition.models import Exemplar, Layer, Rule, Status
from disposition.retrieval import Retrieved, retrieve
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


class RetrievalTest(unittest.TestCase):
    def _store(self, tmp: str, *, build_index: bool = True) -> Store:
        store = Store(pathlib.Path(tmp))
        store.scaffold("java")

        exemplars = [
            Exemplar(
                id=Exemplar.make_id("Retry.java", 10, RETRY_CODE),
                code=RETRY_CODE,
                language="java",
                layer=Layer.LANGUAGE,
                source="Retry.java",
                provenance="bootstrap",
            ),
            Exemplar(
                id=Exemplar.make_id("Parse.java", 3, PARSE_CODE),
                code=PARSE_CODE,
                language="java",
                layer=Layer.LANGUAGE,
                source="Parse.java",
                provenance="bootstrap",
            ),
            Exemplar(
                id=Exemplar.make_id("Stream.java", 5, STREAM_CODE),
                code=STREAM_CODE,
                language="java",
                layer=Layer.LANGUAGE,
                source="Stream.java",
                provenance="bootstrap",
            ),
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
                Rule(key="streams", text="Favor streams for collection mapping.",
                     status=Status.PROVISIONAL, layer=Layer.LANGUAGE, confidence=0.4),
            ],
            "java",
        )

        if build_index:
            embedder = LocalEmbedder()
            vectors = embedder.embed([ex.code for ex in exemplars])
            index = VectorIndex(embedder.dim)
            index.add_many(
                [(ex.id, vectors[i], {"source": ex.source}) for i, ex in enumerate(exemplars)]
            )
            index.save(store.index_dir(Layer.LANGUAGE, "java"))
        return store

    def test_ranks_relevant_exemplar_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            got = retrieve(
                store,
                task="add retry with exponential backoff on IOException",
                language="java",
                embedder=LocalEmbedder(),
            )
            self.assertIsInstance(got, Retrieved)
            self.assertTrue(got.exemplars)
            self.assertEqual(got.exemplars[0].source, "Retry.java")

    def test_returns_active_style_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            got = retrieve(store, task="parse a date string", language="java")
            keys = {r.key for r in got.rules}
            # Personal + Language rules merged by the Cascade.
            self.assertEqual(keys, {"early-returns", "retries", "streams"})

    def test_k_rules_keeps_confirmed_caps_provisional(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            got = retrieve(store, task="anything", language="java", k_rules=2)
            statuses = [r.status for r in got.rules]
            # Two confirmed rules fill the budget; the provisional one is dropped.
            self.assertEqual(len(got.rules), 2)
            self.assertTrue(all(s is Status.CONFIRMED for s in statuses))

    def test_rebuilds_index_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp, build_index=False)
            self.assertFalse(VectorIndex.exists(store.index_dir(Layer.LANGUAGE, "java")))
            got = retrieve(
                store,
                task="map users to their names with a stream",
                language="java",
                embedder=LocalEmbedder(),
                k_exemplars=3,
            )
            self.assertTrue(got.exemplars)
            self.assertEqual(got.exemplars[0].source, "Stream.java")

    def test_confirmed_rule_filters_violating_exemplar(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            # A Confirmed rule that forbids "stream" should drop the stream exemplar.
            store.save_rules(
                Layer.LANGUAGE,
                store.load_rules(Layer.LANGUAGE, "java")
                + [Rule(key="no-streams", text="Avoid stream in mapping code.",
                        status=Status.CONFIRMED, layer=Layer.LANGUAGE, confidence=0.9)],
                "java",
            )
            got = retrieve(
                store,
                task="map users to their names with a stream",
                language="java",
                embedder=LocalEmbedder(),
                k_exemplars=5,
            )
            self.assertNotIn("Stream.java", {ex.source for ex in got.exemplars})

    def test_empty_store_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(pathlib.Path(tmp))
            store.scaffold("java")
            got = retrieve(store, task="whatever", language="java", embedder=LocalEmbedder())
            self.assertEqual(got.exemplars, [])
            self.assertEqual(got.rules, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
