# Onboarding always runs an adaptive, non-leading Interview

Bootstrap mines a developer's *outputs*, meaning finished, committed code. But a lot of Style is *reasoning*: how someone approaches a problem and why they pick one approach over another. That is invisible in static code, which only shows the result. So elicitation is not just a cold-start fallback for developers with no history. It is a universal onboarding step that captures a dimension Bootstrap structurally cannot.

Decision: onboarding **always runs an Interview**, for every developer, alongside Bootstrap. Here is its shape:
- **Don't lead with the hard questions.** Open with low-stakes context, language then platform, before any scenario.
- **Scenario tests, not multiple choice.** Small, easy-but-revealing coding scenarios (for example, "here's a class with a data race producing out-of-sync results across threads, how would you change it?"). How the developer resolves it exposes their architectural leanings (locking vs immutability vs atomics vs redesigning the shared state away).
- **Two response modes.** Edit the code directly in the IDE and reply "Done" (preferred, since it yields a real Exemplar), or describe the approach. Describing works best when they narrate their stream of consciousness through `/voice`, which captures the *reasoning*, not just the outcome.
- **Adaptive and diagnostic.** The interviewer models what it already knows (from Bootstrap and prior answers) versus what it still needs, and aims follow-ups to fill the gaps in the fewest questions. It is not a fixed script.

**Non-leading is load-bearing.** A scenario that telegraphs the "expected" answer captures the tool's bias, not the developer's, and that poisons the Authorship Test at its source. Scenarios have to allow several legitimate answers and reveal which one is *theirs*.

**Signal authority follows the do-vs-declare split** (it mirrors ADR 0008's induce-vs-author distinction). When the developer *does* something, like an IDE edit that resolves a scenario, that yields a real **Exemplar plus a Provisional Rule** (one instance, still needs corroboration). When the developer *declares* a principle during narration ("I always kill shared state rather than lock"), we treat it as a developer-**authored Confirmed Rule**, because they stated it *as* a rule, not just did it once. Either way the Rule stays subject to Drift and delta-queries (ADR 0009), so an odd answer to one contrived scenario never gets locked in for good.

This makes the Interview a first-class capture source alongside Bootstrap, Correction, and Ambient Capture, and it is part of the v1 slice, not a phase-2 add-on. The ongoing Drift delta-queries (ADR 0009) are basically micro-Interviews triggered by change.

Considered and rejected: elicitation only as a cold-start fallback (wastes the reasoning signal for developers who happen to have history, which is most of them); a fixed non-adaptive question battery (asks what Bootstrap already knows, wasting the developer's patience).
