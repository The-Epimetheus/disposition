"""Tests for the Store's own interface: merging, indexing, the Active Style.

Runs standalone (`python3 tests/test_store.py`) and under unittest.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.embeddings import LocalEmbedder, get_embedder
from disposition.index import VectorIndex
from disposition.models import Exemplar, Layer, Rule, Status
from disposition.project import save_project_rules
from disposition.store import Store


def _store() -> Store:
    store = Store(pathlib.Path(tempfile.mkdtemp()))
    store.scaffold("java")
    return store


def _rule(key: str, text: str = "x", status=Status.PROVISIONAL, layer=Layer.LANGUAGE) -> Rule:
    return Rule(key=key, text=text, status=status, layer=layer)


class TestMergeRules(unittest.TestCase):
    def test_newest_wins_by_key(self):
        store = _store()
        store.merge_rules(Layer.LANGUAGE, [_rule("naming", "old")], "java")
        added = store.merge_rules(Layer.LANGUAGE, [_rule("naming", "new")], "java")
        self.assertEqual(added, 0)  # same key: replaced, not added
        rules = store.load_rules(Layer.LANGUAGE, "java")
        self.assertEqual([(r.key, r.text) for r in rules], [("naming", "new")])

    def test_keep_existing_never_clobbers(self):
        store = _store()
        store.merge_rules(Layer.LANGUAGE, [_rule("naming", "earned")], "java")
        added = store.merge_rules(
            Layer.LANGUAGE,
            [_rule("naming", "seed"), _rule("logging", "seed")],
            "java",
            keep_existing=True,
        )
        self.assertEqual(added, 1)  # only the genuinely new key landed
        by_key = {r.key: r.text for r in store.load_rules(Layer.LANGUAGE, "java")}
        self.assertEqual(by_key, {"naming": "earned", "logging": "seed"})

    def test_empty_merge_is_a_no_op(self):
        store = _store()
        self.assertEqual(store.merge_rules(Layer.LANGUAGE, [], "java"), 0)
        self.assertEqual(store.load_rules(Layer.LANGUAGE, "java"), [])


class TestRebuildIndex(unittest.TestCase):
    def test_rebuild_covers_every_exemplar_and_persists(self):
        store = _store()
        exemplars = [
            Exemplar(
                id=Exemplar.make_id("A.java", i, f"int f{i}() {{ return {i}; }}"),
                code=f"int f{i}() {{ return {i}; }}",
                language="java",
                layer=Layer.LANGUAGE,
                source="A.java",
                start_line=i,
            )
            for i in range(3)
        ]
        store.add_exemplars(Layer.LANGUAGE, exemplars, "java")
        size = store.rebuild_index(Layer.LANGUAGE, "java", embedder=LocalEmbedder())

        self.assertEqual(size, 3)
        directory = store.index_dir(Layer.LANGUAGE, "java")
        self.assertTrue(VectorIndex.exists(directory))
        self.assertEqual(len(VectorIndex.load(directory)), 3)

    def test_rebuild_with_no_exemplars_writes_an_empty_index(self):
        store = _store()
        size = store.rebuild_index(Layer.LANGUAGE, "java", embedder=LocalEmbedder())
        self.assertEqual(size, 0)
        self.assertTrue(VectorIndex.exists(store.index_dir(Layer.LANGUAGE, "java")))


class TestActiveStyleLayers(unittest.TestCase):
    def test_without_repo_merges_two_layers(self):
        store = _store()
        store.merge_rules(Layer.PERSONAL, [_rule("naming", "p", layer=Layer.PERSONAL)])
        store.merge_rules(Layer.LANGUAGE, [_rule("naming", "l")], "java")
        style = store.active_style("java")
        self.assertEqual([(r.key, r.layer) for r in style], [("naming", Layer.LANGUAGE)])

    def test_repo_folds_in_the_project_layer(self):
        store = _store()
        repo = tempfile.mkdtemp()
        # A Confirmed Personal rule vs a Provisional Project rule on one key:
        # status is the first precedence key, so Personal must win (ADR 0011).
        store.merge_rules(
            Layer.PERSONAL,
            [_rule("naming", "mine", status=Status.CONFIRMED, layer=Layer.PERSONAL)],
        )
        save_project_rules(
            repo,
            [
                _rule("naming", "house", layer=Layer.PROJECT),
                _rule("imports", "house", status=Status.CONFIRMED, layer=Layer.PROJECT),
            ],
        )
        style = {r.key: r for r in store.active_style("java", repo=repo)}
        self.assertEqual(style["naming"].text, "mine")
        self.assertEqual(style["imports"].layer, Layer.PROJECT)

    def test_confirmed_project_beats_confirmed_personal(self):
        store = _store()
        repo = tempfile.mkdtemp()
        store.merge_rules(
            Layer.PERSONAL,
            [_rule("naming", "mine", status=Status.CONFIRMED, layer=Layer.PERSONAL)],
        )
        save_project_rules(
            repo, [_rule("naming", "house", status=Status.CONFIRMED, layer=Layer.PROJECT)]
        )
        style = {r.key: r for r in store.active_style("java", repo=repo)}
        # Both Confirmed: the more specific layer (sanctioned house style) wins.
        self.assertEqual(style["naming"].text, "house")


class TestGetEmbedder(unittest.TestCase):
    def test_unknown_embedding_model_is_an_error_not_a_shrug(self):
        class Cfg:
            models = {"embedding": "semantic-9000"}

        with self.assertRaises(ValueError):
            get_embedder(Cfg())

    def test_local_is_the_default(self):
        class Cfg:
            models = {"embedding": "local"}

        self.assertIsInstance(get_embedder(Cfg()), LocalEmbedder)


if __name__ == "__main__":
    unittest.main()
