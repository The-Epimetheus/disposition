# Disposition

Disposition is a personalization layer for AI-assisted coding. It learns how one developer likes to write code, then steers an outside AI coding tool to write that same way. The goal is simple: AI-written code should read like the developer wrote it, so it stays easy to maintain by hand.

This repo builds Disposition **the product**. It is a general, reusable tool that any developer installs to set up their own style steering. It is not any one person's style profile. We do test it against the maintainer's own code in this repo, but that is just a test case, not the point.

## Language

**Developer**:
The person who uses Disposition. Their Style gets captured, and their AI output gets steered to match it. Every Style Profile belongs to a Developer. (In this repo the maintainer is also the first Developer, for testing, but the two roles are still separate.)
_Avoid_: user (too vague, since it could mean someone who uses the Developer's software).

**Disposition**:
A steering layer that sits on top of an existing, outside AI coding tool. It captures a developer's style and pushes it into that tool's output. It does not write code itself and owns no model.
_Avoid_: agent, model, assistant (Disposition is none of these, it steers one).

**Hypertrain**:
Shaping an outside AI's output toward the developer's style through heavy context work: prompts, examples, and retrieval. It is **not** weight-level fine-tuning.
_Avoid_: fine-tune, train (those imply changing the model's weights, which Disposition never does).

**Style Service Protocol (SSP)**:
Disposition's own idea. It is the contract for serving a developer's style profile to an outside AI coding tool, on demand. Even though the pitch calls it an "LSP," this is **not** the editor Language Server Protocol.
_Avoid_: LSP, Language Server Protocol (those mean the unrelated editor standard).

**Style**:
Every choice a developer makes when turning a problem into code. That covers formatting, naming and word habits, which constructs they reach for, the setups and scaffolding they trust, and how they lay out architecture. Disposition models **all** of these, not just one.
_Avoid_: formatting, conventions (each names only one slice of Style).

**Style Profile**:
A captured picture of Style at one scope. Profiles stack and cascade. There is a **Personal** profile (a developer's habits across everything), a **Language** profile (their habits in one language), and a **Project** profile (a repo's house style). The **Active Style** for a given task is the merge of whichever layers apply.
_Avoid_: model, config (a profile is neither).

**Cascade**:
The rule for merging profile layers into an Active Style. It uses two keys. First is confirmation status: a Confirmed Rule outranks a Provisional one. Second is layer specificity: Project beats Language beats Personal. So Confirmed-Project beats Confirmed-Personal (sanctioned house style wins), but a Provisional (unsanctioned) Project profile does **not** override a developer's Confirmed Personal Rule. It favors maintainability over personal taste, but only when the house style was actually sanctioned.
_Avoid_: override, inheritance (too loose; "Cascade" is the real term).

**Project Profile**:
The house-style layer of the Cascade. The Personal and Language profiles are private and local, but a Project Profile is **shared**. It gets committed in the repo (`.disposition/`) and travels with the code like `.editorconfig` does. It is built automatically from the repo's real code and confirmed by a maintainer. Until someone confirms it, it stays a weak Provisional prior.
_Avoid_: house rules, repo config (a Project Profile is a Style Profile scoped to a repo, and it runs on the same Rule and Exemplar machinery).

**Bootstrap**:
The first pass that fills a Style Profile from a developer's existing code (repos, git history). It solves the cold-start problem. We treat it as a *prior*, not as ground truth, because old code is full of deadline hacks, habits the developer has outgrown, and work merged in from other people. By default it only learns from code the developer actually wrote (checked via blame) and weights recent code more heavily. The developer can **disavow** specific repos, files, or authors to leave them out.
_Avoid_: import, ingest (too mechanical; Bootstrap is a starting prior that later signal refines).

**Rule**:
A short, plain-language statement of an explicit style preference ("prefers early returns," "reaches for `Result` over exceptions"). Rules are the readable, editable backbone of a Style Profile. A Rule is either **Confirmed** (the Developer accepted it, or it auto-accepted, and it actively steers generation) or **Provisional** (induced but not yet sanctioned, so it has weak or no influence while it waits for confirmation). Rules come from inducing over Exemplars and Corrections, or the Developer writes them by hand.
_Avoid_: setting, config (a Rule is a taste statement, not a toggle).

**Induction**:
Distilling plain-language candidate Rules from a developer's code and Corrections. Induced Rules are *proposed*, not active. The Developer confirms, edits, or rejects them. The one exception is high-confidence mechanical patterns, which auto-accept.
_Avoid_: extraction, mining (Induction specifically makes proposed Rules for confirmation, not raw data).

**Exemplar**:
A snippet of the developer's real code, kept in the profile's corpus and pulled in at generation time as a few-shot example. Exemplars carry the feel of Style that Rules can't put into words. When an Exemplar directly conflicts with an applicable **Confirmed** Rule, the Rule wins. One dissenting Exemplar just yields, but *lots* of dissent gets read as [[Drift]].
_Avoid_: sample, template (an Exemplar is real past work, not a generic pattern).

**Forced Injection**:
Making sure the Active Style is in the AI's context on every single generation. It gets there through the host tool's always-on context slot, or the proxy prepends it. We do not count on the model to go pull the SSP server itself.
_Avoid_: prompt, context (name the guarantee, not the payload).

**Verification Gate**:
A check that runs after generation. It grades the AI's output against the Style Profile and bounces off-style output back for a redo before the human ever sees it. This is the active defense of the Authorship Test. It turns "we asked" into "we checked."
_Avoid_: linter, validator (those check correctness or format; the Gate checks Style-envelope fit).

**Interview**:
An onboarding step that always runs. It actively draws out a developer's Style by watching how they solve small, high-signal, **non-leading** coding scenarios. That captures *reasoning and approach*, which Bootstrap (static code) can't show. It opens with easy context (language, platform), then poses scenario tests. The developer answers by editing code in their IDE (preferred) or by narrating their thinking out loud (for example through `/voice`). It is **adaptive**: the interviewer tracks what it already knows versus what it still needs, and aims its follow-ups to fill the gaps in as few questions as possible. It runs for *every* developer, not just cold-start, and it works alongside Bootstrap.
_Avoid_: quiz, survey (an Interview probes reasoning through real coding scenarios, not multiple choice), onboarding wizard (too generic).

**Correction**:
A **behavior-preserving** edit a developer makes to code that Disposition's steered AI produced. Same behavior, different form. This is the highest-value learning signal, because it is a direct "this, not that" and shows exactly when the developer picks one approach over another. A behavior-*changing* edit is a bug fix, **not** a Correction, and we leave it out of Style learning to keep the signal clean.
_Avoid_: edit, fix (a Correction is specifically a behavior-preserving, taste-carrying change to AI output; a bug fix is neither).

**Ambient Capture**:
Quietly watching the developer code by hand going forward (suggestions they accept or reject, edits they type themselves). It reinforces and updates the profile in between Corrections.
_Avoid_: telemetry, tracking (those sound like surveillance; this is style signal, scoped and owned by the developer).

**Drift**:
A lasting change in a developer's Style over time (say, moving from a dependency-injection pattern toward a generic inheritance pattern). The profile is recency-weighted and self-aging, so slow or mechanical Drift gets absorbed on its own. But substantive Drift that contradicts a **Confirmed** Rule gets surfaced to the Developer as a **delta query** for sign-off, instead of getting silently re-learned.
_Avoid_: decay, staleness (those name the profile-aging mechanism, not the developer-side change that Drift means).

**Style Envelope**:
The whole range of code variants that still read as a given developer's work. A problem has many valid solutions inside one developer's envelope. Disposition aims to keep AI output inside that envelope, not to reproduce one exact keystroke sequence.
_Avoid_: fingerprint (implies one fixed pattern instead of a range).

**Authorship Test**:
The success metric for Disposition. In a blind review, someone shown human-written and Disposition-steered code can't tell which is which. Their accuracy drops toward a coin flip. "Identical" output is the north star we talk about; passing the Authorship Test is the thing we can actually measure.
_Avoid_: accuracy, correctness (those grade whether the code works, not whether it reads as the developer's).
