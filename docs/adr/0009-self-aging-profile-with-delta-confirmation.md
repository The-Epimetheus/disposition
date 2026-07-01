# The profile is self-aging, but substantive Drift is confirmed, not silently absorbed

The Authorship Test targets the *current* developer, not a composite ghost of every era of their git history. So the profile is **recency-weighted and self-aging**. Exemplars and Rule-confidence decay with age, fresh Corrections and Ambient Capture outweigh old signal, and a Confirmed Rule that today's Corrections keep contradicting is evidence the Rule is stale, not that today's edits are wrong.

But aging is not fully silent. Gradual, mechanical Drift gets absorbed on its own. **Substantive Drift that contradicts a Confirmed Rule**, especially architectural shifts (say, moving from a dependency-injection pattern to a generic inheritance bias), gets surfaced to the Developer as a **delta query** ("continued evidence suggests you've moved from X to Y, update your profile?") before the Confirmed Rule is demoted or replaced.

This mirrors ADR 0008's confirmation philosophy. Mechanical patterns move without friction, but un-sanctioning something the human explicitly sanctioned also needs the human. It keeps the profile tracking present-you while stopping a run of unusual recent edits from silently overwriting a deliberate, confirmed preference.

Considered and rejected: a static archive profile (ossifies into a no-one composite); fully silent self-aging (a short burst of atypical edits could quietly erase a deliberate Confirmed Rule); manual era/epoch versioning (homework most developers won't do, so we keep it as a possible power-user feature).
