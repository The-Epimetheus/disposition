"""Tests for the Java chunker's heuristic fallback (disposition.java).

tree_sitter is not installed in this environment, so `parse_java` exercises the
brace-and-signature fallback here. These import only stdlib + disposition, so
they run via `python3 tests/test_java.py` and via `unittest discover`.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.java import CodeChunk, chunk_java_file, has_tree_sitter, parse_java

SAMPLE = """package demo;

public class Widget {
    private int count;

    public Widget(int count) {
        this.count = count;
    }

    public int increment() {
        if (count < 0) {
            count = 0;
        }
        return ++count;
    }

    public String label() {
        return "count = " + count;
    }
}
"""


class JavaFallbackTest(unittest.TestCase):
    def setUp(self):
        # This suite is meaningful only on the fallback path.
        self.assertFalse(has_tree_sitter(), "expected tree-sitter absent")

    def test_extracts_methods_not_class(self):
        chunks = parse_java(SAMPLE)
        self.assertTrue(chunks, "expected at least one chunk")
        self.assertTrue(all(c.kind == "method" for c in chunks))
        names = {c.name for c in chunks}
        self.assertEqual(names, {"Widget", "increment", "label"})

    def test_line_spans_are_plausible(self):
        chunks = {c.name: c for c in parse_java(SAMPLE)}
        # `increment` starts at its signature line and closes on its own `}`.
        inc = chunks["increment"]
        self.assertEqual(inc.start_line, 10)
        self.assertEqual(inc.end_line, 15)
        self.assertIn("return ++count;", inc.code)
        # Spans are ordered and non-degenerate.
        for c in chunks.values():
            self.assertLessEqual(c.start_line, c.end_line)

    def test_nested_braces_do_not_close_early(self):
        inc = {c.name: c for c in parse_java(SAMPLE)}["increment"]
        # The inner `if { ... }` must not terminate the method body early.
        self.assertIn("count = 0;", inc.code)

    def test_string_braces_are_ignored(self):
        src = 'class C {\n  String f() {\n    return "{ not a brace";\n  }\n}\n'
        chunks = parse_java(src)
        self.assertEqual([c.name for c in chunks], ["f"])
        self.assertEqual(chunks[0].kind, "method")

    def test_class_level_when_no_methods(self):
        src = "public interface Marker {\n}\n"
        chunks = parse_java(src)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].kind, "class")
        self.assertEqual(chunks[0].name, "Marker")

    def test_control_flow_not_mistaken_for_method(self):
        # A bare `if (...) {` at top level must not be captured as a method.
        src = "class C {\n  void run() {\n    for (int i = 0; i < 3; i++) {\n      i++;\n    }\n  }\n}\n"
        names = {c.name for c in parse_java(src)}
        self.assertEqual(names, {"run"})

    def test_parse_never_raises_on_garbage(self):
        # Unbalanced braces / nonsense must degrade, not throw.
        for bad in ["", "{{{", "class Oops {", "%%% not java %%%"]:
            self.assertIsInstance(parse_java(bad), list)

    def test_chunk_java_file_roundtrip(self):
        with tempfile.NamedTemporaryFile("w", suffix=".java", delete=False, encoding="utf-8") as fh:
            fh.write(SAMPLE)
            path = fh.name
        chunks = chunk_java_file(path)
        self.assertTrue(all(isinstance(c, CodeChunk) for c in chunks))
        self.assertEqual({c.name for c in chunks}, {"Widget", "increment", "label"})

    def test_missing_file_returns_empty(self):
        self.assertEqual(chunk_java_file("/no/such/file.java"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
