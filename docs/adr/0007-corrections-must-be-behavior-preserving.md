# Only behavior-preserving edits count as Corrections

Corrections are Disposition's highest-value learning signal, but not every edit to AI output is a style signal. If a developer edits AI code because it was *wrong* (a bug), and we feed that diff into Style learning, we teach Disposition that the developer "prefers" a behavior they were only fixing. That poisons the profile.

Decision: a **Correction is strictly a behavior-preserving edit**. Same behavior, different form. Behavior-*changing* edits are bug fixes, and we leave them out of Style learning entirely. We capture candidate edits by diffing AI-generated spans against later developer edits (git-anchored), plus an explicit reinforce command.

Each candidate runs through a **layered** behavior-preservation check:
1. **Sound static.** AST equivalence modulo formatting, naming, and reordering proves preservation for the easy cases.
2. **Test-based.** If the AI code and the edited code both go green on the same suite, that is strong evidence.
3. **LLM classifier** for the genuine middle that the first two can't reach.

The uncertainty policy is **strict default-exclude**: when confidence is low, drop the candidate. The costs are lopsided. A false "preserving" poisons the profile with functional intent, while a false "changing" only loses one datapoint, so we lean hard toward exclusion.

This is strict on purpose. We accept lower learning *volume* in exchange for clean signal. A future reader will ask "why not learn style from all edits to AI output?" The answer: bug-fix edits carry functional intent, not taste, and mixing them in degrades the profile.

Considered and rejected: treating every edit to AI output as weak style signal (higher volume, but it corrupts the profile with functional changes).
