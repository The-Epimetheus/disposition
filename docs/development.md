# Development

This is the M0 skeleton. It runs, but the real capture, induction, retrieval,
and verification stages are not built yet. See `v1-implementation-plan.md` for
the milestone plan.

## Requirements

- Python 3.11 or newer (M0 uses the standard-library `tomllib`).

## Install (editable)

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Try it

```
disposition init                 # scaffold ~/.disposition and write config
disposition status               # show the Active Style (empty until M1)
disposition version
```

You can also run it without installing:

```
python3 -m disposition status
```

## Run the tests

The Cascade tests need nothing but the standard library:

```
python3 tests/test_cascade.py
```

## Register the MCP server with Claude Code

After `pip install -e .`:

```
claude mcp add disposition -- disposition serve
```

For M0 the server exposes one tool, `active_style`, which returns the merged
Active Style as text. Forced Injection and the Verification Gate come later.

## Versioning

Versions are managed by [bump](https://github.com/launchfirestorm/bump).
`bump.toml` is the source of truth.

```
bump print               # v0.1.0  (prefixed, used for git tags)
bump print --no-prefix   # 0.1.0   (PEP 440, used for pyproject and __init__)
bump --patch             # 0.1.0 -> 0.1.1
bump --minor             # 0.1.0 -> 0.2.0
bump --major             # 0.1.0 -> 1.0.0
```

After a version change, sync the Python files and tag:

```
sed -i "s|^version = .*|version = \"$(bump print --no-prefix)\"|" pyproject.toml
sed -i "s|^__version__ = .*|__version__ = \"$(bump print --no-prefix)\"|" disposition/__init__.py
bump tag                 # annotated git tag, e.g. v0.1.0
```

Note: sync pyproject.toml from `bump print --no-prefix`, not `bump update`.
As of bump 7.1.0 `bump update` writes the "v" prefix, which PEP 440 rejects.

## What M0 includes

- `disposition/config.py` - load and write `~/.disposition/config.toml`.
- `disposition/models.py` - the `Rule` type, plus `Status` and `Layer`.
- `disposition/cascade.py` - the two-key merge (ADR 0002, ADR 0011).
- `disposition/store.py` - read and write `rules.yaml`, compute the Active Style.
- `disposition/cli.py` - the `version`, `init`, `status`, and `serve` commands.
- `disposition/server.py` - the hello-world MCP server.
