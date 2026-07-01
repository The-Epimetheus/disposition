"""The proxy SSP path: inject the Active Style, intercept for the Gate.

This is the second transport for the Style Service Protocol, co-equal with the
MCP server (ADR 0001, ADR 0003), for tools that do not speak MCP. Where MCP
lets a client *pull* the Style envelope, the proxy sits in the request path and
does two things in one round trip:

* FORCE-INJECT -- it retrieves the task-scoped Active Style and prepends it to
  the prompt as a non-negotiable style preamble, so the model cannot generate
  without the developer's rules and exemplars in front of it.
* INTERCEPT -- it runs the model's output back through the Verification Gate
  (`gate.verify`), regenerating against any cited violations before returning.

`Proxy` is deliberately a plain library wrapper: no sockets, no HTTP. A real
HTTP proxy would import this and call `Proxy.steer(prompt)` once per intercepted
request, mapping the request body to `prompt`/`task` and the response back from
the returned text. Keeping the mechanism in a pure method makes both the wiring
and the tests trivial.
"""

from __future__ import annotations

from ..gate import Violation, verify
from ..llm import LLM, get_llm
from ..retrieval import Retrieved, retrieve
from ..store import Store


# The banner that frames the injected block. The model is told, in no uncertain
# terms, that this is a constraint on the output, not background reading.
_PREAMBLE_HEADER = (
    "You must follow this developer's personal coding style. The rules and "
    "exemplars below are directives, not suggestions; produce output that "
    "honours every confirmed rule and matches the exemplars' texture."
)


def _render_preamble(retrieved: Retrieved, language: str) -> str:
    """Render the Style envelope as a forced preamble for the prompt.

    Compact but legible: each rule as a citable bullet, each exemplar as a
    fenced block, so the model sees both the explicit rules and the tacit
    texture before it writes a line.
    """
    lines = [_PREAMBLE_HEADER, "", "STYLE RULES:"]
    if retrieved.rules:
        for rule in retrieved.rules:
            lines.append(f"- [{rule.key}] ({rule.status.value}) {rule.text}")
    else:
        lines.append("- (none captured yet)")

    if retrieved.exemplars:
        lines += ["", "STYLE EXEMPLARS:"]
        for ex in retrieved.exemplars:
            label = ex.source or ex.provenance or ex.id
            lines += [f"# {label}", f"```{language}", ex.code.strip("\n"), "```"]
    return "\n".join(lines)


class Proxy:
    """Force-inject the Active Style and intercept the response for the Gate.

    One `steer` call demonstrates the whole SSP proxy loop: retrieve -> inject
    -> generate -> verify -> (regenerate against violations) -> return. An HTTP
    proxy would own the socket and delegate the per-request work to `steer`.
    """

    def __init__(
        self,
        store: Store,
        *,
        language: str = "java",
        llm: LLM | None = None,
        embedder=None,
        max_regens: int = 3,
    ) -> None:
        self.store = store
        self.language = language
        # Generation runs on the configured generation model (or a wired fake).
        self.llm = llm or get_llm()
        self.embedder = embedder
        self.max_regens = max_regens

    def steer(self, prompt: str, *, task: str = "") -> str:
        """Inject the Active Style, generate, verify, and return the final text.

        `task` scopes retrieval (falling back to `prompt` when unspecified) so
        the injected exemplars match the job at hand. After the first
        completion we hand the output to the Gate with a `regenerate` callback
        that re-asks the model with the previous attempt and the cited
        violations; the Gate loops up to `max_regens` before escalating. Either
        way we return the Gate's final output -- clean if it passed, or the last
        attempt if it escalated.
        """
        retrieved = retrieve(
            self.store,
            task=task or prompt,
            language=self.language,
            embedder=self.embedder,
        )
        preamble = _render_preamble(retrieved, self.language)

        # FORCE-INJECT: the style preamble leads; the caller's prompt follows.
        injected = f"{preamble}\n\nTASK:\n{prompt}"
        output = self.llm.complete(injected)

        def _regenerate(previous: str, violations: list[Violation]) -> str:
            # Re-ask with the same forced preamble plus the judge's citations,
            # so the retry is anchored to exactly what it broke.
            cites = "\n".join(f"- [{v.cite}] {v.detail}" for v in violations)
            retry = (
                f"{preamble}\n\nTASK:\n{prompt}\n\n"
                f"Your previous attempt violated the style:\n{cites}\n\n"
                f"PREVIOUS OUTPUT:\n{previous}\n\n"
                "Rewrite it so it honours every rule above."
            )
            return self.llm.complete(retry)

        # INTERCEPT: the Gate re-reads the output and regenerates on violations.
        result = verify(
            output,
            retrieved,
            llm=self.llm,
            task=task or prompt,
            max_regens=self.max_regens,
            regenerate=_regenerate,
        )
        return result.final_output
