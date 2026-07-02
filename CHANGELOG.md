# Changelog

All notable changes to this project are documented here.
The format follows Keep a Changelog; versions are managed with bump.

## [Unreleased]

- Embeddings: new semantic embedder (fastembed, local ONNX model) behind `models.embedding = "semantic"` via the `[semantic]` extra; retrieval rebuilds transparently when the configured embedder's dimension changes
- Capture: one CapturePipeline persists Exemplars and Rules as a unit (add, reindex, merge); bootstrap, interview, ambient, and correction all cross that one seam now
- Gate: `disposition verify` now runs the full loop (deterministic tier, judge, regenerate up to budgets.max_regens, escalate); `--write` saves the fix, `--judge-only` keeps the old one-pass report
- Cascade: `active_style` takes an optional repo and folds in its committed PROJECT house style; `status` and `verify` gained `--repo` and `inject` uses its repo automatically
- Config: every key in config.toml is honored now (budgets.max_regens, budgets.retrieval_top_k, models.embedding); unknown embedding models error instead of being ignored
- Store: new `merge_rules` and `rebuild_index` own rule merging and the index schema; six duplicated copies across capture and distill modules removed
- Docs: truth pass over README, plan, CONTEXT, and development.md (hash embedder named for what it is, no AST tier claim, voice narration described honestly, stale M0 notes replaced)

## [v1.0.0] - 2026-07-01

- Docs: mark v1 (M0-M4) complete; real install and usage in README
- M4: phase 2 (project layer, proxy, cold-start, adaptive interview, injection)
- M3: signal quality (classifier tiers, deterministic gate, self-aging + drift)

## [v0.3.0] - 2026-07-01

- M2: richer capture (passive corrections, ambient capture, voice narration)
- Trim v0.2.0 changelog to post-v0.1.0 commits

## [v0.2.0] - 2026-07-01

- M1: thin thread (bootstrap, interview, induction, retrieval, injection, gate, correction)
- Induce over a sampled, batched exemplar set
- Fix induction JSON truncation: bigger token budget + salvage
- Add rule consolidation pass to merge near-duplicate rules
