# Disposition v1: Implementation Plan

> Status: complete. Milestones M0 through M4 are all built and released (see `CHANGELOG.md` and the releases page). Everything below the milestone sequence was the plan; it now describes shipped code.

The first vertical slice. Scope (from the grilling session): **Claude Code host, Java, solo (Personal + Language layers), Python stack.** The Project layer, the proxy adapter, and cold-start archetypes were phase 2 and are now built.

This plan sits downstream of the twelve ADRs in `docs/adr/`. Where v1 deliberately simplifies an ADR's full design, it says so. Nothing here quietly contradicts a recorded decision.

---

## 1. Components

A local Python package (`disposition/`), a CLI, and an MCP server. All state lives on disk under `~/.disposition/` (ADR 0004, fully local).

| Module | What it does | ADRs |
|---|---|---|
| `store` | Save Rules, Exemplars, and the index. Compute the **Active Style** with the two-key Cascade merge | 0002, 0011 |
| `capture/bootstrap` | Pull author-filtered Java history into Exemplars and embeddings (a *prior*) | 0004 |
| `capture/interview` | CLI scenario Interview. `do` gives an Exemplar plus a Provisional Rule, `declare` gives a Confirmed Rule | 0012 |
| `capture/correction` | AI-span registry plus the behavior-preservation classifier. Feeds Rules and Exemplars | 0007 |
| `induction` | LLM distills candidate Rules. Auto-accept the mechanical ones, triage the rest | 0008 |
| `retrieval` | Pull task-relevant Rules and Exemplars at generation time (v1 uses strategy **B**) | 0003 |
| `ssp` | MCP server (on-demand retrieval) plus the `CLAUDE.md` generator (Forced Injection) | 0001, 0003 |
| `gate` | Adversarial LLM judge. Up to 3 targeted regens, then hand off to the human | 0003, 0006 |
| `adapters/claude_code` | Wire up `CLAUDE.md` and register the MCP server | 0001 |
| `cli` | Onboarding, triage, `reinforce`, status and inspect | none |

**Dependencies:** `mcp` (official SDK), `anthropic` (LLM calls), `tree-sitter` plus `tree-sitter-java` (AST), a local embedding model and a local vector store (say `sqlite` + `numpy`, or `lancedb`), `pygit2` or a git subprocess (blame, span anchoring), and `typer` (CLI).

---

## 2. On-disk layout (`~/.disposition/`)

```
~/.disposition/
├── config.toml                 # model ids, injection strategy (default: B), budgets
├── profiles/
│   ├── personal/
│   │   ├── rules.yaml          # READABLE source of truth: text, status (confirmed|provisional),
│   │   │                       #   confidence, provenance, timestamps (for self-aging)
│   │   ├── exemplars/          # referenced snippets (source path + span + captured code)
│   │   └── index/              # rebuildable embedding index (opaque, derived cache)
│   └── java/                   # same shape, Language layer
├── provenance/                 # AI-generated span records for Correction attribution
└── interview/                  # captured Interview answers plus narration transcripts
```

Rules stay readable and hand-editable, which is the whole trust mechanism. The index is just a derived cache, and you can rebuild it from the Exemplars anytime.

---

## 3. Milestone 1: the thin thread (the actual first build)

One narrow path that touches every stage end-to-end on your real Java code. It is stubbed where noted. Later milestones deepen each stage to its full ADR design.

1. **Onboard**
   - *Interview:* a fixed 3-scenario battery. Ask language, then platform, then the scenarios. The developer answers by editing in their IDE and replying `Done`, or by typing a description. **Stub:** fixed battery, no adaptive gap-model yet (ADR 0012 adaptivity lands in M4). Text narration is fine for now; `/voice` comes in M2.
   - *Bootstrap:* pull in a handful of author-filtered Java files as Exemplars plus embeddings.
2. **Induce, then confirm** - one LLM pass over the Exemplars produces candidate Rules. Auto-accept the mechanical ones, CLI-triage the top-N, and leave the rest Provisional (ADR 0008).
3. **Steer** - dynamic retrieval (strategy B) builds `CLAUDE.md` and serves an MCP retrieval tool. Force-inject it into Claude Code.
4. **Generate** - drive Claude Code on a Java task (you kick it off by hand).
5. **Verify** - the adversarial LLM-judge gate runs. Up to 3 targeted regens, then it escalates to you (ADR 0006). **Stub:** LLM-judge tier only; the deterministic and AST tiers come in M3.
6. **Learn** - an explicit `disposition reinforce <span>` command captures a Correction. Behavior preservation runs through the LLM classifier with strict default-exclude (ADR 0007). **Stub:** explicit command only (passive span-diff lands in M2); LLM classifier tier only (AST and test tiers come in M3).

**Definition of done for M1:** you run onboarding, Disposition steers Claude Code to write a Java function you judge to be inside your envelope, the gate visibly catches one off-style attempt and regenerates, and `reinforce` measurably changes the profile. Success is **your** Authorship Test call on a few tasks.

---

## 4. Milestone sequence

- **M0, Skeleton:** package, `config.toml`, `store` with the Cascade merge, CLI shell, and an MCP server hello-world registered in Claude Code.
- **M1, Thin thread:** section 3. Prove the loop on your Java.
- **M2, Richer capture:** passive Correction span-diff watcher (git-anchored), Ambient Capture, and `/voice` narration in the Interview.
- **M3, Signal quality:** AST and test classifier tiers (ADR 0007), the deterministic gate tier (ADR 0006), the self-aging profile, and Drift delta-queries (ADR 0009).
- **M4, Phase 2:** the Project layer with maintainer confirm (ADR 0011), the proxy adapter (ADR 0001), cold-start archetypes, the adaptive Interview gap-model (ADR 0012), and injection strategies A and C plus user config (ADR 0003 / Q19).

---

## 5. Deferred implementation questions (not blocking)

These are easier to answer against running code than more whiteboarding:

- **Interview scenario battery** - which non-leading scenarios reveal the most per question.
- **Rule-induction prompt** - how the LLM should phrase and scope the Rules it induces.
- **Gate escalation UX** - what "rope in the human" actually looks like inside Claude Code.
- **Correction attribution window** - how long an edit still counts as a Correction against an AI span.
- **Embedding model** - which local code-embedding model to use for retrieval.
