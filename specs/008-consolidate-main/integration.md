# Branch integration ledger

Date: 2026-10-17. Starting main:
`1e9065f62b4c6da460941e35a6bc3d49fc673ba3`.
Refactor first committed locally as `6659277` on `codex/production-readiness-refactor`.
No original branch has been deleted while integration is in progress.
Combined source is committed as `a906d70`; ancestry record `a9150da` retains all
twelve assessed original tips as ancestors. Its tree was checked equal to the
reviewed combined source, so recording ancestry did not substitute old content
for the recovered implementation. Final validation evidence is recorded separately.

The first push was rejected by GitHub's private-email protection (GH007). Before
any successful publication, only the four new local commits were recreated using
the authenticated account's public noreply identity. Every commit tree and message
was verified unchanged; all original remote commits retain their exact identity.
The local-to-public mappings are `6659277` to `bfbc06c`, `b6b851e` to `a906d70`,
`3639d7b` to `a9150da`, and `5695b24` to `5e088a1`. The private local identities
remain only in the verified local recovery bundle. Account privacy and branch
protection settings were not weakened.

The complete original refs/history were saved and `git bundle verify` passed for
`branches-before-integration.bundle` in the OS temporary directory
`careeros-main-integration-20261017`. A final recovery bundle must include the
integrated work before branch deletion. These bundles are recovery evidence, not
release artifacts or a substitute for committing the source.
A checksum-verified durable copy of the pre-publication recovery bundle is also
retained in private Git metadata at `.git/careeros-recovery/2026-10-17/`, outside
tracked source and temporary-cache cleanup. The final bundle is created there
before deleting any integrated refs.

| Original remote branch | Original tip | Content assessment / integration decision |
| --- | --- | --- |
| codex/careeros-job-search-workbench | 57cd2c360042d844cddb918d8ef66e6d794edb90 | Already integrated through #49/#50. First three commits' tree equals 9b2871a; backend/desktop/requirements of the final workbench commit equal squash 37d35ce. Later main contains router/security and subsequent functionality improvements; retain those. |
| codex/configurable-providers-agent-parity | ed6fc844ef0aa7ca61f02a2a45ddc27635fcc9ac | Recover missing configurable desktop providers. Current proposal workflow, authenticated desktop bridge and constitution 2.0.1 supersede obsolete direct agent writes/publication. Assign a new migration after the current head; its old revision collides with existing agent-work migration. |
| dependabot/docker/compatible-backend-images-26df7c4d23 | bb7bb6461e6ac9c4cd315e1c715a2f56236c66e9 | Integrate verified Python image 3.12.15 with its official OCI digest and matching contracts. |
| dependabot/docker/docker/ollama/compatible-ollama-images-243800f558 | ceb1c97b999ed7f4b3056cbfdf586849306097ef | Integrate verified base 0.34.3 with matching source/archive digest and security patches. The first protected build and runtime smoke passed; its scan found six fixable HIGH findings. T015 updates Go, x/net and Ubuntu OpenSSL, with rebuilt-image scanning still required. A base-only bump would leave the old binary. |
| dependabot/docker/frontend/compatible-frontend-images-c4034bb791 | 88c1565bcf74332c95daac6cee8a5f63d51fdf34 | Integrate verified Node 24.21.0 / nginx 1.31.6 image digests and matching contracts. |
| dependabot/github_actions/compatible-actions-9a64edb76f | d28dfa2788e95efeb562b2001a4e47b0a157c632 | Integrate five officially verified pinned action SHAs, updating contract tests together. |
| dependabot/npm_and_yarn/frontend/compatible-frontend-dependencies-d4ea7b047b | 19491617f0de265908703b565414a68d41b8bdbb | All 17 remaining grouped updates integrated; the Vitest family is included separately. Fresh-cache hash-verified npm ci installed 272 packages, the complete tree has valid peers, and full/production audits both report zero vulnerabilities. React/DOM resolve to 19.3.1, router 8.4.0, Vite 7.3.7, Playwright 1.64.1 and Tauri API/CLI 2.12.1. Router loading now waits for authentication, reducing real unused login boot code while preserving routing/blockers and the original budgets. |
| dependabot/npm_and_yarn/frontend/undici-7.29.0 | 4b694cc6941bf84fcd3e9d4b74345d422065a2e5 | Original 7.29.0 version/integrity was already integrated; superseded by installed and audited security version 7.29.1. |
| dependabot/npm_and_yarn/frontend/vitest-4.1.11 | bc2b19185cc3bc87ab535998c770dc78c2224f54 | Integrated Vitest and coverage 4.1.11 coherently, with the matching resolved family; complete frontend coverage passed. The stale-cache E404 conclusion is withdrawn. |
| dependabot/pip/compatible-python-dependencies-091adf42d4 | c6008cfb4db239852a476d7226c89511cf2ce0ef | Verify all proposed pins through official PyPI; adopt the 15 remaining installable upgrades with regenerated locks. Keep newer PyJWT/pypdf and already integrated MCP/pip-tools security versions. |
| dependabot/pip/pyjwt-2.15.0 | 150f3d0b1c006f0c2b7d39889273e24e2d5063e7 | Superseded by verified 2.15.1 in refactor 6659277; no downgrade. |
| dependabot/pip/pypdf-6.19.0 | c128d863804d77faf110d9142b2c6f95d8da6a7c | Superseded by verified 6.21.0 in refactor 6659277; no downgrade. |

## Main protection

Verified through GitHub API: main requires signed commits, linear history, zero
mandatory approving reviews and six strict required checks. Administrators are
also bound by the protections; force pushes and main deletion are forbidden.
Repository PR integration permits squash only. Required checks are Backend,
Frontend, Rust, Containers, Release supply-chain evidence and Linux x64. CodeQL
has no current-user bypass.

The combined work must use the permitted integration path. An unavailable
dependency or failed required audit does not authorize disabling protections,
fabricating a successful status or deleting the only remaining work branch.
Main publication and final branch deletion remain pending until the real checks
and content verification permit them.

## Correction to historical package availability evidence

The failed 007 npm audit and its cached CLI output remain genuine historical
executions. They do not establish present package unavailability. Independent
008 verification found that a new cache resolves the published versions while
the old cache still returns E404, even with `--prefer-online`. Availability and
final vulnerability results in this feature must use fresh-cache registry
evidence and the final lock, rather than repeat that historical inference.
