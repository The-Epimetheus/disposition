# Project profiles are auto-derived, maintainer-confirmed, and shared in-repo

The Project layer is house style, and the Cascade lets it override personal taste. So how it gets authored and who sanctions it is a governance decision, not just a data-source choice.

Decision: a Project profile is **auto-derived plus maintainer-confirmed**. It is induce-then-confirm (ADR 0008) lifted one level up. Candidate house Rules come from the repo's *real* committed code (weighting maintainer-marked canonical files and recent code over treating every contributor equally), then a **maintainer confirms or edits** them. The confirmed profile gets **committed in the repo** (`.disposition/`) and travels with the code like `.editorconfig` does.

This is the first deliberately *shared* artifact, which is a departure from the private, local Personal profile (ADR 0004). It is consistent, though: house style is a team convention, not personal IP.

Governance follows sanction. Imposing Project-over-Personal is legitimate only because a maintainer sanctioned it. So precedence is two-key, confirmation status first, then layer (this refines ADR 0002). An auto-derived, **unconfirmed** Project profile stays **Provisional** and acts as a weak prior that does **not** override a contributor's Confirmed Personal Rules. A repo with no maintainer using Disposition never silently overrides its contributors.

Considered and rejected: auto-derived-only (nobody sanctioned it, so it has no authority to override personal style, and it risks lowest-common-denominator aggregation); maintainer-authored-only (authoritative but aspirational, and it drifts from what the code actually looks like).

Status: accepted, implementation deferred to phase 2 (v1 is solo, Personal and Language only).
