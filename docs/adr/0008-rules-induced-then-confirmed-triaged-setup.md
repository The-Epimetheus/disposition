# Rules are induced then confirmed, and setup is triaged, not a gauntlet

Rules are the readable spine of a profile, but most of a developer's style is unconscious. So a tool that only records hand-written Rules captures very little, while one that auto-writes Rules makes machine guesses the "source of truth" and breaks the trust story.

Decision: Rules are **induced** (an LLM pass distills them from Exemplars and Corrections) but **proposed, not active**. The Developer confirms, edits, or rejects them. The one exception: **high-confidence mechanical patterns auto-accept** (formatting, casing), since they are low-stakes and easy to verify. So a Rule is either **Confirmed** (it steers generation) or **Provisional** (induced, unsanctioned, weak or no influence).

At **initial setup** the same machinery runs, but confirmation is **triaged**. Auto-accept the mechanical Rules, then run a **bounded, prioritized review session** (highest-signal, most-frequent, most-surprising first) that the Developer can stop anytime. Everything left unreviewed stays **Provisional** and resolves *organically through use*. It gets promoted when ongoing Corrections and the Verification Gate back it up, and dropped when they don't. Setup gives you a solid confirmed core in minutes, and the profile deepens as the Developer works.

Considered and rejected: hand-written Rules only (misses unconscious style, which is most of it); auto-accept all induced Rules (unreviewed machine guesses as source of truth, which breaks trust); confirm every induced Rule at setup (a confirmation gauntlet that kills onboarding).
