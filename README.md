# Disposition

**AI-written code that reads like you wrote it.**

Disposition is a personalization layer for AI-assisted coding. It learns how you like to write code, then steers your AI coding tool to write that same way.

> Status: early. The design is done (see `CONTEXT.md` and `docs/adr/`), and the v1 build is planned in `docs/v1-implementation-plan.md`. There is no installable release yet. The install and usage steps below describe the v1 flow we are building toward, not something you can run today.

---

## Why it exists

If you let AI write all your code, it writes in its own style, not yours. That is fine right up until you have to fix it by hand. The person who can actually maintain a piece of code is the person who wrote it, and if a machine wrote it in machine-style, that person is nobody.

So you get stuck. The AI is fast, but the code it leaves behind does not read like yours, and the day the AI is down or the change is too subtle to hand off, you are maintaining a codebase that feels like a stranger's.

Disposition fixes that. It captures how *you* write, then makes the AI write that way too. You keep the speed of AI, and you keep code you can actually own.

## What it does

- **Learns your style.** It looks at your existing code, asks you a few short coding questions, and watches the edits you make to AI output. From all of that it builds a profile of how you write: naming, formatting, which constructs you reach for, the setups you trust, and how you lay out architecture.
- **Steers the AI.** Every time your AI tool generates code, Disposition pushes your style into the request. It does not hope the model remembers. It forces your style in on every generation.
- **Checks the result.** After the AI writes something, Disposition grades it against your profile. If the output does not read like you, it sends it back for a redo before you ever see it.
- **Keeps up with you.** Your style changes over time. Disposition ages its profile so it tracks the current you, and it checks in with you before dropping anything you explicitly confirmed.

Disposition owns no model and writes no code itself. It steers a tool you already use. It is not fine-tuning either. It shapes output through context (prompts, examples, retrieval), not by changing model weights.

## What it will do

The first version (v1) is deliberately narrow so we can prove the whole loop works end-to-end:

- Host: Claude Code
- Language: Java
- Scope: solo developer (your personal and per-language style)

After that, the roadmap adds:

- **Team style.** A shared, per-repo house style that travels with the code, confirmed by a maintainer.
- **More hosts.** A proxy path so tools that do not speak MCP still get steered.
- **Richer learning.** Passive capture of your edits, voice narration during setup, and deeper checks on whether an edit changed behavior or just style.

The full plan lives in `docs/v1-implementation-plan.md`.

## Install (planned, not yet available)

The v1 install is meant to be simple:

```
pip install disposition        # not published yet
disposition init               # set up ~/.disposition and register with Claude Code
```

`init` walks you through onboarding: it reads your existing Java code, asks a few short coding questions, and builds your starting profile.

## Use (planned, not yet available)

Once set up, you mostly forget it is there. It runs behind your AI tool.

```
disposition status             # see your profile: rules, examples, confidence
disposition reinforce <span>   # tell it "this edit is how I like it" and update the profile
```

Day to day, you just use Claude Code as normal. Disposition injects your style, checks the output, and quietly learns from the edits you make.

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
