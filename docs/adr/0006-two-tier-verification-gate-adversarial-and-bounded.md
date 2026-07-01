# The Verification Gate is two-tier, adversarial, and bounded by human escalation

The Gate (ADR 0003) is what actually defends the Authorship Test, so how it grades really matters. It is **two-tier**. Cheap deterministic checks form a floor for the mechanical layers (naming, banned constructs, formatting). An **LLM-judge** handles the tacit idiom and architecture layers, which are the layers where AI code most gives itself away and where deterministic checks are blind.

The judge has three deliberate properties:
1. **Adversarially framed.** It is a *separate* call told to "find where this deviates from the Developer's envelope and cite the Rule or Exemplar it violates," never "is this fine?" A judge asked to approve code it just generated will rubber-stamp it.
2. **Exemplar-grounded.** It contrasts the output against retrieved real code from the Developer, not just against abstract Rules. That is what catches tacit drift.
3. **Bounded, targeted regeneration.** A failed check feeds the *specific* cited violation back for a focused regenerate, capped at **3 rounds**. If it hits the cap without landing inside the envelope, Disposition **escalates to the human** with the flagged deviations instead of looping. The human is the final authority, never an infinite retry.

Considered and rejected: deterministic-only (blind to idiom and architecture); LLM-judge-only (skips the free deterministic mechanical floor); non-adversarial judging (rubber-stamps); unbounded regeneration (burns cost and can never converge on genuinely hard cases).
