# Disposition v1 is built in Python

Disposition has to analyze Java, run local embeddings and retrieval, orchestrate LLM calls (induction, the adversarial judge, the behavior-preservation classifier), and serve MCP while generating `CLAUDE.md`.

Decision: build the v1 PoC in **Python**, for the fastest path to a working end-to-end thread. It has the richest LLM and embedding ecosystem, the official MCP SDK, and `tree-sitter-java` for AST work.

Accepted costs, chosen deliberately over Kotlin/JVM:
- **Second-class Java analysis.** `tree-sitter-java` is shallower than Eclipse JDT or JavaParser. We judge it good enough for v1's AST-equivalence-modulo-formatting tier of the behavior-preservation classifier (ADR 0007). If it turns out too shallow, we can shell out to a JVM analyzer later.
- **Thesis waiver.** Disposition's own pitch is "you can maintain it by hand," and the maintainer is strongest in Java and Kotlin. So building the tool in Python contradicts that thesis for this codebase. We waive it for the PoC and revisit if Disposition graduates past prototype.

Considered and rejected for v1: Kotlin/JVM (best-in-class native Java analysis right where the difficulty concentrates, and it satisfies the maintainability thesis, but it has a thinner LLM and ML ecosystem and more plumbing, which loses PoC speed); TypeScript (best MCP and Claude Code integration, but the weakest Java analysis).

Status: accepted for the v1 PoC. This is a PoC-scoped choice, not a permanent platform commitment.
