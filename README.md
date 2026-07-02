# Disposition

**AI-written code that reads like you wrote it.**

Disposition is a personalization layer for AI-assisted coding. It learns how you like to write code, then steers your AI coding tool to write that same way.

> Status: v1 is built. Milestones M0 through M4 are complete and released (see the releases page and `CHANGELOG.md`). It runs today: install from source and go. It is not published to PyPI yet, and it is a proof of concept, so expect rough edges.

---

## Why it exists

If you let AI write all your code, it writes in its own style, not yours. That is fine right up until you have to fix it by hand. The person who can actually maintain a piece of code is the person who wrote it, and if a machine wrote it in machine-style, that person is nobody.

So you get stuck. The AI is fast, but the code it leaves behind does not read like yours, and the day the AI is down or the change is too subtle to hand off, you are maintaining a codebase that feels like a stranger's.

Disposition fixes that. It captures how *you* write, then makes the AI write that way too. You keep the speed of AI, and you keep code you can actually own.

## What it does

- **Learns your style.** It looks at your existing code, asks you a few short coding questions, and watches the edits you make to AI output. From all of that it builds a profile of how you write: naming, formatting, which constructs you reach for, the setups you trust, and how you lay out architecture.
- **Steers the AI.** You inject your style into the tool's always-on context (for Claude Code, a marked block in `CLAUDE.md`), so every generation in that repo starts with your rules and examples in front of it. It does not hope the model remembers.
- **Checks the result.** Run the gate on what the AI wrote and Disposition grades it against your profile. If the output does not read like you, the gate regenerates it, up to a configured cap, and only escalates to you if it still cannot get inside your envelope.
- **Keeps up with you.** Your style changes over time. Disposition ages its profile so it tracks the current you, and it checks in with you before dropping anything you explicitly confirmed.

Disposition owns no model and writes no code itself. It steers a tool you already use. It is not fine-tuning either. It shapes output through context (prompts, examples, retrieval), not by changing model weights.

## What's built in v1

The v1 target is Claude Code, Java, and starts solo but includes a shared team layer. The whole loop works end to end:

- **Capture.** Bootstrap mines your own code (author-filtered) into examples. The interview draws out your reasoning with small coding scenarios, answered live or as a narration transcript (a typed stream of thought; live voice capture is not built yet), and adapts its follow-ups to the gaps. Corrections learn from your edits to AI output, both when you point them out and passively by watching a tracked span. Ambient capture folds in new commits each time you run it.
- **Distill.** Induction turns your examples into plain-language rules, auto-accepting the mechanical ones and leaving the rest for you. Consolidation merges near-duplicates so the profile stays tidy.
- **Steer.** Your style gets forced into context (three injection strategies, your choice) through Claude Code's `CLAUDE.md` and MCP server, plus a proxy library you can wire in front of tools that do not speak MCP.
- **Check.** The verification gate grades output against your profile, cheap deterministic checks first, then an adversarial judge, and regenerates off-style code before you see it.
- **Keep it honest.** The profile self-ages, decaying stale guesses, and surfaces drift for your sign-off instead of silently overwriting a preference you confirmed. A shared, in-repo project layer carries team house style (and folds into steering whenever you point a command at that repo), and cold-start archetypes seed a profile when you have no history yet.

Out of the box, retrieval matches your task to examples with a deterministic local hashing embedder: no downloads, but the matching is lexical. For real semantic matching, install the extra (`pip install -e ".[semantic]"`) and set `models.embedding = "semantic"` in the config. That runs a local embedding model instead; it downloads once, then works offline like everything else.

The full milestone plan lives in `docs/v1-implementation-plan.md`.

## Install

Not on PyPI yet, so install from source:

```
git clone https://github.com/The-Epimetheus/disposition
cd disposition
pip install -e .               # on a PEP 668 system: pip install --user --break-system-packages -e .
disposition init               # set up ~/.disposition
```

The LLM-backed steps need an Anthropic key: `export ANTHROPIC_API_KEY=...`. See `docs/development.md` for details, including registering the MCP server with Claude Code.

## Use

A typical loop, from your code to steered, checked AI output:

```
disposition bootstrap <repo> --author "You"     # mine your own code into examples
disposition interview                            # or --adaptive, or --transcript <file>
disposition induce --auto                        # distill rules from the examples
disposition consolidate                          # merge near-duplicate rules
disposition status                               # see your Active Style

disposition inject --repo <repo> --task "..."    # force your style (and the repo's house style) into <repo>/CLAUDE.md
#   ...drive Claude Code on the task, then:
disposition verify --file Out.java --task "..."  # gate: judge, regenerate off-style code, escalate
#   --write saves the corrected output; --judge-only just reports

disposition track <file> --start N --end M       # mark AI code, then edit freely
disposition watch                                # sweep up behavior-preserving corrections
disposition observe <repo>                        # capture new commits as ambient signal
disposition age; disposition drift               # profile hygiene: decay + drift review
```

Day to day you mostly use Claude Code as normal; Disposition injects your style, checks the output, and learns from your edits.

## Why you should use it

- **You keep AI speed without losing your codebase.** Fast code that still reads like yours.
- **You can maintain what the AI writes.** When the AI is down or you go in by hand, the code already looks like something you wrote, so there is nothing to relearn.
- **It stays private.** Everything runs on your machine. Your profile and your code never leave it. There is no Disposition cloud. See `docs/adr/0004-fully-local-no-cloud.md`.
- **You stay in control.** Disposition proposes, you confirm. It does not treat machine guesses as the source of truth, and it does not silently overwrite a preference you set on purpose.

## Learn more

- `CONTEXT.md`: the glossary. Every term Disposition uses, defined.
- `docs/adr/`: the design decisions, and why each one went the way it did.
- `docs/v1-implementation-plan.md`: the v1 build plan and milestones.

## License

Disposition is **source available**, not classic open source. The code is public, and you are free to use it, modify it, self-host it, and run it inside your own business. What you cannot do is **Sell** it: you cannot resell it, offer it as a paid hosted service, or ship a product whose value comes mostly from this code. If you want to do any of that, reach out and we will sort out a commercial license.

The license is the Apache License 2.0 with the Commons Clause condition on top. The full text is in `LICENSE`. The Commons Clause is what carves out the "no selling it" part; everything else is standard Apache 2.0.
