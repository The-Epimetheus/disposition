# Style profiles cascade, and project style wins over personal

A style profile is not a single global "you." Style is scoped. A developer's habits shift by language, and a shared repo has a house style that has to override personal taste so teammates can read the code. So we model profiles as three cascading layers, **Personal, Language, and Project**, merged into an **Active Style** at request time.

On conflict, the more specific layer wins: **Project beats Language beats Personal.** That is a deliberately surprising choice for a product sold on *personal* style. We picked it because the pitch's real justification is maintainability ("the person who can fix it wrote it," and on a team that is whoever reads the house style), and that matters more than reproducing individual quirks in shared code. On solo projects only the Personal and Language layers are active, so the "feels like me" experience is safe there.

Considered and rejected: a single global profile per developer (ignores code-switching and collides with team repos); personal-always-wins (breaks team maintainability, which is the whole justification).

**Refinement (see ADR 0011):** precedence is not purely by layer. It uses two keys, **confirmation status first, then layer specificity.** A Confirmed-Project Rule still beats a Confirmed-Personal Rule (sanctioned house style wins), but a *Provisional* (unsanctioned) Project profile does not override a developer's Confirmed Personal Rule. Authority comes from sanction, and only sanctioned house style earns the right to override personal taste.
