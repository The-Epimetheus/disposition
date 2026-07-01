"""Tests for the proxy SSP path (ADR 0001/0003), driven entirely by FakeLLM.

Covers the two proxy outcomes and the force-injection guarantee:
  (a) the first generation passes the Gate -> returned unchanged;
  (b) the first generation violates the style, a regenerate produces a clean
      one -> the regenerated text is returned;
  and in both cases the forced style preamble is present in what the model saw.

Runs standalone (`python3 tests/test_proxy.py`) and under unittest discovery.
No network: generation and judging both use a callable FakeLLM.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.adapters.proxy import Proxy
from disposition.embeddings import LocalEmbedder
from disposition.llm import FakeLLM
from disposition.models import Layer, Rule, Status
from disposition.store import Store


class _Recorder:
    """Callable FakeLLM script that records every prompt the model sees.

    `completions` feed `complete()` calls in order; `jsons` feed the Gate's
    `judge()` calls in order. Every call appends `(kind, prompt)` to `prompts`
    so tests can assert what the model actually received.
    """

    def __init__(self, completions, jsons):
        self.completions = list(completions)
        self.jsons = list(jsons)
        self.prompts: list[tuple[str, str]] = []

    def __call__(self, prompt: str, kind: str):
        self.prompts.append((kind, prompt))
        return self.completions.pop(0) if kind == "complete" else self.jsons.pop(0)


# A confirmed rule we can look for in the injected preamble. Not "mechanical",
# so the deterministic tier ignores it and outcomes hinge on the scripted judge.
_RULE = Rule(
    key="early-returns",
    text="Prefer early returns over nested conditionals.",
    status=Status.CONFIRMED,
    layer=Layer.LANGUAGE,
)

# Clean, plausible output: no trailing whitespace / tabs / System.out, so the
# deterministic tier stays silent and the judge alone decides.
_CLEAN = "int f(int x) {\n    if (x < 0) return 0;\n    return x;\n}"
_DIRTY = "int f(int x) {\n    int r;\n    if (x < 0) { r = 0; } else { r = x; }\n    return r;\n}"


def _store(tmp: str) -> Store:
    store = Store(pathlib.Path(tmp))
    store.scaffold("java")
    store.save_rules(Layer.LANGUAGE, [_RULE], language="java")
    return store


class ProxyTest(unittest.TestCase):
    def test_passes_first_generation_returned_as_is(self):
        # (a) judge returns no violations on the first output -> return it.
        rec = _Recorder(completions=[_CLEAN], jsons=[[]])
        with tempfile.TemporaryDirectory() as tmp:
            proxy = Proxy(_store(tmp), llm=FakeLLM(rec), embedder=LocalEmbedder())
            out = proxy.steer("write f", task="clamp negatives to zero")

        self.assertEqual(out, _CLEAN)
        # Force-injection: the first thing the model saw carried the style.
        first_kind, first_prompt = rec.prompts[0]
        self.assertEqual(first_kind, "complete")
        self.assertIn("early-returns", first_prompt)
        self.assertIn("early returns", first_prompt)
        self.assertIn("write f", first_prompt)

    def test_regenerates_once_then_returns_clean(self):
        # (b) first output violates; regenerate is clean on the second pass.
        violation = [{"cite": "early-returns", "detail": "nested if/else, no early return"}]
        rec = _Recorder(completions=[_DIRTY, _CLEAN], jsons=[violation, []])
        with tempfile.TemporaryDirectory() as tmp:
            proxy = Proxy(_store(tmp), llm=FakeLLM(rec), embedder=LocalEmbedder())
            out = proxy.steer("write f", task="clamp negatives to zero")

        self.assertEqual(out, _CLEAN)
        # Exactly one regeneration: two completions, two judge passes.
        completes = [p for k, p in rec.prompts if k == "complete"]
        self.assertEqual(len(completes), 2)
        # Both the original and the retry carried the forced preamble...
        for prompt in completes:
            self.assertIn("early-returns", prompt)
        # ...and the retry cited the violation it had to fix.
        self.assertIn("nested if/else", completes[1])


if __name__ == "__main__":
    unittest.main()
