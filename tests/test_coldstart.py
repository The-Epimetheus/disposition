import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import tempfile
import unittest
from pathlib import Path

from disposition.coldstart import ARCHETYPES, apply_archetype, list_archetypes
from disposition.models import Layer, Status
from disposition.store import Store


class ColdStartTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_list_archetypes(self):
        names = list_archetypes()
        self.assertEqual(set(names), set(ARCHETYPES))
        self.assertIn("android-defensive", names)

    def test_apply_seeds_provisional_rules(self):
        name = "functional-immutable"
        added = apply_archetype(self.store, name, language="java")
        self.assertEqual(added, len(ARCHETYPES[name]))

        rules = self.store.load_rules(Layer.LANGUAGE, "java")
        self.assertEqual(len(rules), len(ARCHETYPES[name]))
        for rule in rules:
            self.assertEqual(rule.status, Status.PROVISIONAL)
            self.assertEqual(rule.provenance, "archetype")
            self.assertEqual(rule.layer, Layer.LANGUAGE)

    def test_merge_by_key_does_not_re_add(self):
        name = "minimalist"
        first = apply_archetype(self.store, name)
        second = apply_archetype(self.store, name)  # idempotent by key
        self.assertEqual(first, len(ARCHETYPES[name]))
        self.assertEqual(second, 0)

    def test_unknown_name_raises(self):
        with self.assertRaises(ValueError) as ctx:
            apply_archetype(self.store, "no-such-archetype")
        self.assertIn("no-such-archetype", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
