# Style Service Protocol, delivered over MCP, not the editor LSP

Disposition gets pitched as a "personalized LSP," but it is on purpose **not** an editor Language Server Protocol server. LSP is built for deterministic, symbol-level answers (completions, diagnostics, hovers), and it has no natural slot for steering a chat-based, multi-file generative agent. So we reframe "LSP" as **Style Service Protocol (SSP)**, which is Disposition's own contract for serving a developer's style profile to an outside AI coding tool.

We build SSP mostly as an **MCP server**. It is AI-native, model-agnostic, and tools like Claude Code and Cursor consume it on demand. As a fallback, we put a **proxy** in front of the model API for closed tools that don't speak MCP.

Considered and rejected: a literal LSP server (wrong shape for generative steering); proxy-only (it works everywhere but is brittle and opaque, so we keep it as the escape hatch).

**Amendment (see ADR 0003):** the proxy gets promoted from mere fallback to a first-class path. Reliable steering means you have to *force* style into context and *intercept* output to verify it. The proxy is the one place both are possible for tools that won't host always-on rules, so it is now co-equal with MCP, not a last resort.
