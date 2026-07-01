# Fully local, the profile and corpus never leave the machine

Disposition is sold on trust and maintainability. Its profile is a sensitive distillation of how a developer thinks, built from source that is often owned by an employer. Being a cloud service that holds everyone's code would directly undercut that promise, and the security-conscious employers who most want house-style consistency would ban it outright.

Decision: everything runs on the developer's own machine. That means the Style Profile, the Exemplar corpus, retrieval, and the Verification Gate. The only data that leaves is data that already leaves without Disposition: the prompts going to whatever AI model the developer already uses. There is no Disposition cloud, not even opt-in profile sync. Cross-device sync is the developer's own problem to solve (for example, syncing the profile files through their existing dotfiles or git).

Consequences: we carry no custody risk and need no server infrastructure. In exchange we give up easy cross-device sync and any pooled improvement across users.

Considered and rejected: cloud SaaS (easy sync and central learning, but the custody risk is catastrophic and it poisons IP policy); local-first with opt-in encrypted profile sync (still more surface than the trust story wants, so we keep it as a possible future, not a launch feature).
