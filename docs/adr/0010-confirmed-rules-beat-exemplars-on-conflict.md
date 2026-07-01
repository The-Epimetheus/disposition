# Confirmed Rules beat Exemplars on direct conflict, and aggregate dissent is Drift

The Cascade (ADR 0002) resolves cross-layer precedence, but the injected Active Style can still contradict itself inside a single scope. The sharpest case is when a retrieved Exemplar (real code) violates an applicable Confirmed Rule (stated taste).

Decision: on **direct conflict, the Confirmed Rule wins.** A Confirmed Rule is a deliberate statement the human explicitly accepted. An Exemplar is unsanctioned historical texture that might predate the Rule or be a one-off exception. Exemplars supply texture *when there is no governing Rule*, but they don't get to defy one. At injection, Exemplars that violate an applicable Confirmed Rule get filtered or down-ranked out of the retrieval set.

The subtlety: a *single* dissenting Exemplar yields silently, but a *sustained pattern* of recent Exemplars or Corrections against a Rule is not a conflict to resolve. It is **Drift** (ADR 0009), and it routes to a delta query. Rule-vs-Rule conflicts within a layer resolve by confidence times recency, and a persistent same-layer contradiction gets surfaced as a profile-health issue.

This runs deliberately counter to "show, don't tell," where you might expect real code to beat a stated rule. It doesn't, because the Rule carries explicit human sanction that the Exemplar lacks. The Exemplar's dissent only earns authority in aggregate, and at that point it becomes Drift.
