# Style is force-injected and verified, never just pulled

Disposition's whole value rides on style *reliably* landing in AI output. MCP tool-calls are optional. The model decides whether to call the SSP server, and even when you hand it Rules it can ignore them. So a pull-only design bets the product on the model choosing to ask, and it won't do that reliably.

Instead we do two things. **Forced Injection** guarantees the Active Style is in context on every generation (through the host's always-on context slot, or the proxy prepending it). And a **Verification Gate** grades the output against the profile and regenerates off-envelope results before the human sees them. On-demand Exemplar *retrieval* still flows through the MCP server, but the baseline style floor gets pushed and checked, not hoped for.

Consequence: the proxy becomes a first-class path (this amends ADR 0001). It is the only place style can be both forced in and intercepted for verification in tools that won't host always-on rules.

Considered and rejected: pull-only through MCP (clean, but unreliable, which is a non-starter for a product whose whole promise is reliable style).
