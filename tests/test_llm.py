"""Tests for the LLM wrapper, exercised entirely through FakeLLM (no network).

Runs standalone (`python3 tests/test_llm.py`) and under unittest discovery.
"""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from disposition.llm import FakeLLM, LLM, LLMError, get_llm


class TestFakeLLMScripted(unittest.TestCase):
    def test_list_popped_in_order(self):
        fake = FakeLLM(["first", "second"])
        self.assertEqual(fake.complete("a"), "first")
        self.assertEqual(fake.complete("b"), "second")

    def test_exhausted_list_raises(self):
        fake = FakeLLM([])
        with self.assertRaises(LLMError):
            fake.complete("a")

    def test_callable_receives_prompt_and_kind(self):
        seen = {}

        def script(prompt, kind):
            seen["prompt"] = prompt
            seen["kind"] = kind
            return "ok"

        fake = FakeLLM(script)
        self.assertEqual(fake.complete("hello"), "ok")
        self.assertEqual(seen, {"prompt": "hello", "kind": "complete"})

    def test_complete_stringifies_non_string(self):
        fake = FakeLLM([{"a": 1}])
        self.assertEqual(fake.complete("x"), '{"a": 1}')


class TestFakeLLMJson(unittest.TestCase):
    def test_json_returns_python_object_directly(self):
        payload = {"violations": [1, 2, 3]}
        fake = FakeLLM([payload])
        self.assertIs(fake.json("prompt"), payload)

    def test_json_parses_plain_string(self):
        fake = FakeLLM(['{"k": "v"}'])
        self.assertEqual(fake.json("p"), {"k": "v"})

    def test_json_strips_json_code_fence(self):
        fake = FakeLLM(['```json\n{"k": 1}\n```'])
        self.assertEqual(fake.json("p"), {"k": 1})

    def test_json_strips_bare_code_fence(self):
        fake = FakeLLM(["```\n[1, 2, 3]\n```"])
        self.assertEqual(fake.json("p"), [1, 2, 3])

    def test_json_callable_kind_is_json(self):
        fake = FakeLLM(lambda prompt, kind: {"kind": kind})
        self.assertEqual(fake.json("p"), {"kind": "json"})

    def test_json_bad_value_raises(self):
        fake = FakeLLM([12345])
        with self.assertRaises(LLMError):
            fake.json("p")

    def test_json_salvages_truncated_array(self):
        # A response cut off mid-object (token cap) still yields the complete
        # objects rather than failing the whole batch.
        truncated = '[{"key": "a", "v": 1}, {"key": "b", "v": 2}, {"key": "c'
        fake = FakeLLM([truncated])
        result = fake.json("p")
        self.assertEqual([r["key"] for r in result], ["a", "b"])


class TestGetLLM(unittest.TestCase):
    def test_returns_explicit_fake(self):
        fake = FakeLLM(["x"])
        self.assertIs(get_llm(fake=fake), fake)

    def test_env_flag_yields_fake(self):
        prev = os.environ.get("DISPOSITION_FAKE_LLM")
        os.environ["DISPOSITION_FAKE_LLM"] = "1"
        try:
            self.assertIsInstance(get_llm(), FakeLLM)
        finally:
            if prev is None:
                os.environ.pop("DISPOSITION_FAKE_LLM", None)
            else:
                os.environ["DISPOSITION_FAKE_LLM"] = prev


class TestRealLLMLazy(unittest.TestCase):
    def test_construction_does_not_need_key(self):
        # Building an LLM must not touch the network or require a key.
        llm = LLM(model="claude-opus-4-8")
        self.assertEqual(llm.model, "claude-opus-4-8")

    def test_call_without_key_raises_llmerror(self):
        prev = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with self.assertRaises(LLMError):
                LLM(model="m").complete("hi")
        finally:
            if prev is not None:
                os.environ["ANTHROPIC_API_KEY"] = prev


if __name__ == "__main__":
    unittest.main()
