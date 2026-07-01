# Disposition steers AI output only, it is not a hand-coding assistant

The pitch closes on "when the AI is down or you go in by hand, you can actually maintain this." Read too literally, that sounds like an invitation to build in-editor help (completions, snippets in your idiom). That would drag literal LSP-shaped work back in and contradict ADR 0001.

Decision: hand-maintainability is an **emergent consequence**, not a feature. Disposition's surface is exactly this: capture Style, steer AI output, verify it (the Authorship Test). The maintainability promise is already fully delivered by making AI output indistinguishable from the developer's hand-code. When the AI is down, the developer just codes in a codebase that already reads like theirs, with no help from Disposition.

This is an explicit non-goal: no real-time editor completions, no per-editor typing assist. Those belong to a different product with latency budgets and per-editor integrations, and we turn them down on purpose.
