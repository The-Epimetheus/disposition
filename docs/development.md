# Development

Disposition v1 is built: capture, induction, retrieval, injection, the
Verification Gate, and profile hygiene all work end to end. See
`v1-implementation-plan.md` for what shipped in each milestone.

## Requirements

- Python 3.11 or newer (config reading uses the standard-library `tomllib`).
- An Anthropic API key (`export ANTHROPIC_API_KEY=...`) for the LLM-backed
  commands: `induce`, `consolidate`, `verify`, `reinforce`, `drift`, `project`,
  and the adaptive interview. Everything else runs fully offline.

## Install (editable)

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

On a PEP 668 (externally managed) system without venv support:

```
pip install --user --break-system-packages -e .
```

Java AST chunking is an optional extra (`pip install -e ".[java]"`). Without
it, a heuristic brace-counting parser is used instead.

## Try it

```
disposition init                 # scaffold ~/.disposition and write config
disposition bootstrap <repo>     # mine your code into exemplars
disposition induce --auto        # distill rules from the exemplars
disposition status               # show the merged Active Style
disposition status --repo <r>    # include that repo's house style
```

You can also run it without installing:

```
python3 -m disposition status
```

## Run the tests

The whole suite runs offline, with the LLM faked:

```
DISPOSITION_FAKE_LLM=1 python3 -m unittest discover -s tests -p 'test_*.py'
```

Each test file also runs standalone, for example `python3 tests/test_cascade.py`.

## Register the MCP server with Claude Code

After `pip install -e .`:

```
claude mcp add disposition -- disposition serve
```

The server exposes two tools: `active_style` (the merged Active Style as text)
and `retrieve` (the task-scoped Style envelope: rules plus exemplars).

## Configuration (~/.disposition/config.toml)

Every key is live: change it and behavior changes.

- `models.generation` / `models.judge` - the Anthropic models used.
- `models.embedding` - the embedder; only `"local"` (the offline hashing
  embedder) exists today, and anything else is an error.
- `injection.strategy` - the Forced Injection policy: A full, B dynamic, C hybrid.
- `budgets.max_regens` - how many times the Gate regenerates before escalating.
- `budgets.retrieval_top_k` - the rule budget retrieval injects per task.

## Versioning

Versions are managed by [bump](https://github.com/launchfirestorm/bump).
`bump.toml` is the source of truth.

```
bump print               # v1.0.0  (prefixed, used for git tags)
bump print --no-prefix   # 1.0.0   (PEP 440, used for pyproject and __init__)
bump --patch             # 1.0.0 -> 1.0.1
bump --minor             # 1.0.0 -> 1.1.0
bump --major             # 1.0.0 -> 2.0.0
```

After a version change, sync the Python files and tag:

```
sed -i "s|^version = .*|version = \"$(bump print --no-prefix)\"|" pyproject.toml
sed -i "s|^__version__ = .*|__version__ = \"$(bump print --no-prefix)\"|" disposition/__init__.py
bump tag                 # annotated git tag, e.g. v1.0.0
```

Note: sync pyproject.toml from `bump print --no-prefix`, not `bump update`.
As of bump 7.1.0 `bump update` writes the "v" prefix, which PEP 440 rejects.
