# v1.1 release-contract convergence

Date: 2026-07-20

Decision: implementation converges; the version tag remains unauthorized until this pull request
is merged, required checks pass on the exact merge commit, and a verified signing identity is
available for the annotated tag.

| Requirement | Implementation | Verification | Result |
| --- | --- | --- | --- |
| FR-037 verified source | `release_github.py` recursively requires a GitHub-verified annotated tag, exact candidate commit, and containment in the current default branch, including a safe advancing-head recheck. Source policy runs before attestations and again before/after publication. | Adversarial lightweight, unverified, off-branch, renamed-branch, advancing-head, and pagination tests. | Converged |
| FR-038 exact candidate | `release_assets.py` and `release_contract.py` normalize six targets, reject missing/extra targets, empty files/links/unsafe names/casefold collisions, and bind target/type/name/size/SHA-256, exact checksum names, canonical MIT license content, three SBOMs, and deterministic evidence into 22 public assets. macOS validates and mounts each exact DMG read-only before staging. | Candidate tamper, canonical-license/newline, target coverage, empty package, collision, duplicate-type, mounted-DMG lifecycle/detach, missing/foreign evidence, reproducibility, exact inventory, and checksum tests. | Converged |
| FR-039 durable publication | `publish_github_release.py` discovers all release/asset pages, rejects duplicate/stale/foreign state, never clobbers/deletes, reconciles ambiguous writes, resumes partial drafts, rediscovers sequence immediately before promotion, and verifies exact immutable/latest identity. All tag runs share one cross-tag concurrency group with running-tag cancellation disabled; non-tag runs have no OIDC or write permissions. The runbook states GitHub's one-pending-run limit. | Ambiguous create/upload/publish, partial retry, cross-tag race, later-page duplicate, mismatch, foreign asset, duplicate draft, mutable release, non-latest release, and idempotent no-op tests. | Converged |
| SC-013 adversarial proof | `tests/backend/release/` contains 50 release/version/policy tests and repository hygiene protects the trigger/permission/concurrency split, including an unfiltered pull-request gate. | Full backend suite, static checks, actionlint, frontend/Rust gates, audits, migrations, and performance acceptance passed as recorded in release preparation evidence. | Converged |

## Remaining tag prerequisites

These are deliberately outside this implementation pull request:

1. Merge through protected `main` with all required GitHub checks green on the exact merge commit.
2. Run and review the manual read-only six-platform rehearsal from `main`.
3. Configure a signing identity and create the annotated `v1.1.0` tag so GitHub reports it as
   verified. No signing key was available during this work.
4. Let the tag-push workflow rebuild, attest, verify, and publish. Do not create a release by hand.

No tag, draft release, release asset, or attestation was created while preparing this contract.
