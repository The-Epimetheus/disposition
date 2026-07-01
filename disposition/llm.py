"""Thin wrapper over the Anthropic Messages API plus an offline fake.

`LLM` is the real client: it defers importing `anthropic` until a call is made,
so importing this module never requires a network or an API key. `FakeLLM`
replays scripted responses for tests with zero external dependencies.
`get_llm` is the single entry point: it hands back a fake whenever one is wired
in (explicit arg or the `DISPOSITION_FAKE_LLM` env flag), else a real `LLM`.
"""

from __future__ import annotations

import json
import os

from .config import Config


class LLMError(Exception):
    """Any failure to obtain a usable completion from the model."""


class LLM:
    """Real Claude client. Import + key are checked lazily, at call time."""

    def __init__(self, model: str | None = None) -> None:
        # Resolve the model once, falling back to the configured generation
        # model. Nothing here touches the network or the anthropic package.
        self.model = model or Config.load().models["generation"]

    def _client(self):
        # Import inside the method so module import stays dependency-free, and
        # fail loudly (LLMError) when the key is missing rather than deep in SDK.
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LLMError("ANTHROPIC_API_KEY is not set")
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - anthropic is installed
            raise LLMError("anthropic package is not installed") from exc
        return Anthropic()

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> str:
        """Return the concatenated text of a single completion."""
        client = self._client()
        try:
            resp = client.messages.create(
                model=model or self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # network/SDK errors surface as LLMError
            raise LLMError(str(exc)) from exc
        return "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        )

    def json(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> dict | list:
        """Ask for JSON, strip code fences, parse; one retry, then LLMError."""
        instruction = "\n\nRespond with valid JSON only, no prose or code fences."
        last = ""
        for _ in range(2):  # initial attempt + one retry
            last = self.complete(
                prompt + instruction,
                system=system,
                max_tokens=max_tokens,
                model=model,
            )
            try:
                return _parse_json(last)
            except ValueError:
                continue
        raise LLMError(f"could not parse JSON from model output: {last!r}")


class FakeLLM(LLM):
    """Offline stand-in. Never imports or calls anthropic.

    `scripted` is either a list (values popped in FIFO order) or a callable
    `(prompt, kind) -> value` where kind is "complete" or "json".
    """

    def __init__(self, scripted=None) -> None:
        self.model = "fake"
        self.scripted = scripted

    def _next(self, prompt: str, kind: str):
        if callable(self.scripted):
            return self.scripted(prompt, kind)
        if isinstance(self.scripted, list):
            if not self.scripted:
                raise LLMError("FakeLLM script exhausted")
            return self.scripted.pop(0)
        return self.scripted

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> str:
        value = self._next(prompt, "complete")
        return value if isinstance(value, str) else json.dumps(value)

    def json(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> dict | list:
        value = self._next(prompt, "json")
        # A pre-built python object is returned as-is; a string is parsed
        # (tolerating code fences) so fixtures can be raw JSON text too.
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            return _parse_json(value)
        raise LLMError(f"FakeLLM json() got unusable value: {value!r}")


def _parse_json(text: str) -> dict | list:
    """Strip Markdown code fences and parse JSON. Raise ValueError on failure."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Drop the opening fence line (```json / ```) and the closing fence.
        lines = cleaned.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from exc


def get_llm(config: Config | None = None, fake: LLM | None = None) -> LLM:
    """Return `fake` if supplied or `DISPOSITION_FAKE_LLM` is set, else `LLM`."""
    if fake is not None:
        return fake
    if os.environ.get("DISPOSITION_FAKE_LLM"):
        return FakeLLM()
    cfg = config or Config.load()
    return LLM(model=cfg.models["generation"])
