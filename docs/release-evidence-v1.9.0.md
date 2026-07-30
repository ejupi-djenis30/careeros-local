# CareerOS Local v1.9.0 release preparation evidence

Date prepared: 2026-07-30

Status: candidate metadata and dependency locks are prepared, but v1.9.0 is not tagged or
published. Protected-branch CI and a complete read-only six-target native rehearsal remain
mandatory on the exact merged commit.

## Candidate basis

- The preparation branch starts from `origin/main` commit
  `079bda4766ef74073c6f92eb781932f5da399aba`, whose tree is
  `f4042868168f10666c2d693389f59fea6ec26894`.
- The release audit verified all eight commits after v1.8.0 before release metadata was changed.
- The Agent Access pull-request head
  `ee8635900f1c22d29fc47ea83e7bd462a01ba408` has the same tree
  `f4042868168f10666c2d693389f59fea6ec26894`; this permits its read-only packaging results to be
  attributed to the merged source tree without treating the commit ids as interchangeable.
- All seven authoritative version sources now report `1.9.0`, and the changelog records
  2026-07-30 as the planned release date.

The reviewed implementation records are:

- [CV-first first-use analysis](../specs/001-desktop-career-agent/cv-first-analysis.md)
- [CV-first first-use convergence](../specs/001-desktop-career-agent/cv-first-convergence.md)
- [Dossier-draft analysis](../specs/001-desktop-career-agent/dossier-drafts-analysis.md)
- [Dossier-draft convergence](../specs/001-desktop-career-agent/dossier-drafts-convergence.md)
- [Agent Access center analysis](../specs/001-desktop-career-agent/agent-access-center-analysis.md)
- [Agent Access center convergence](../specs/001-desktop-career-agent/agent-access-center-convergence.md)

## Candidate scope

v1.9.0 removes the first-use dead end for people who begin with an existing CV. CareerOS creates
the minimum revisioned profile before the bounded local source import, leaves extracted candidates
unconfirmed and sends keyboard focus to the explicit fact-review step.

Application dossiers now keep one bounded, revisioned working draft per application in SQLite.
Autosave conflicts preserve the visible form, publication consumes only the exact saved draft in
the same transaction as the immutable dossier event, and portable archive format v6 carries drafts
without breaking inspection or restore of formats v1 through v5.

The authenticated desktop now includes Agent Access management for the existing read-only CLI and
MCP interface. A user chooses scopes, reauthenticates, sees a new bearer once and can revoke every
owned grant. The database retains only a digest. The renderer does not copy or persist the bearer
automatically, and a late issuance is compensating-revoked when the page or session has already
gone away.

The public project Page adds a branded 404 route, explicit no-Jekyll publishing, one canonical
sitemap, a repository-scoped crawler policy and an RFC 9116 security contact that uses private
GitHub Security Advisories.

Direct Python dependency updates and Playwright 1.62.0 are included. The application and
development locks were regenerated after those input changes instead of leaving the release graph
on v1.8.0-era versions.

## Exact remote evidence on the merged source tree

The [CI run 30526098967](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30526098967)
completed successfully on commit `079bda4766ef74073c6f92eb781932f5da399aba`:

- Backend: 1,531 passed and 4 skipped with 81.33% branch coverage. The required local-analysis
  boundary passed 52 tests, and the opt-in performance acceptance slice passed 4 tests.
- Frontend: 70 test files and 396 tests passed. Lint, production build, dependency audit,
  production-license checks and the four-width agenda acceptance gate also passed.
- Rust: formatting, locked Clippy with warnings denied and all 17 tests passed. The Rust
  vulnerability, license and SBOM gates passed.
- Containers: Compose validation, both image builds, read-only frontend smoke, secret and
  configuration scanning, fixed high/critical vulnerability gates and both container SBOMs passed.

The [CodeQL run 30526098985](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30526098985)
and [project Page run 30526098876](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30526098876)
also completed successfully on that commit.

The [Desktop packages run 30524732134](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30524732134)
used the identical source tree. Its supply-chain evidence job and Linux x64 native package,
sidecar, lifecycle and installer smoke passed. The other five native targets were not selected,
and assembly and publication were skipped. This run is useful Linux and supply-chain evidence; it
is not the complete six-target rehearsal required before publication.

## Release-preparation checks

- Python 3.12.13 created an isolated tooling environment by installing
  `requirements-tooling.lock` with hashes. That environment reported pip-tools 7.6.0 and no broken
  requirements.
- The same pinned `pip-compile` regenerated `requirements.lock` and `requirements-dev.lock`.
  Both retain `pywin32==312 ; sys_platform == "win32"` so the shared locks remain installable on
  non-Windows release runners.
- A fresh Python 3.12 environment installed `requirements-dev.lock` with hashes, installed the
  v1.9.0 project editable without dependency resolution and passed `pip check`.
- The full backend suite passed 1,532 tests with 4 expected skips and 81.42% branch coverage in
  that fresh environment. Ruff and mypy passed the same source scopes used by CI.
- All three Python lock audits reported no known vulnerability.
- The full frontend suite passed 70 files and 396 tests. The three production-license tests, ESLint
  and the Vite production build also passed after `npm ci` installed the v1.9.0 lock with no known
  npm vulnerability.
- Locked Cargo metadata and Rust formatting passed.
- `python -m scripts.check_release_versions --expected-tag v1.9.0
  --expected-release-date 2026-07-30` reported
  `RELEASE_VERSION=1.9.0 RELEASE_DATE=2026-07-30 SOURCES=7`.
- The version-contract and adversarial release suites passed 79 tests.
- The repository-hygiene suite passed 13 tests, including the Windows-only `pywin32` marker and
  approved-document inventory checks.

These local checks validate the preparation changes. They do not replace protected-branch CI on
the final commit.

## Claims and boundaries

- CLI and MCP remain read-only. Agent Access does not add write tools, a remote transport or
  automatic credential storage.
- The desktop installer still does not add the source-installed agent commands to the operating
  system `PATH`.
- CareerOS does not send MCP results to a provider, but a configured external client may transmit
  the data it receives. The explicit disclosure acknowledgement remains mandatory.
- Portable ZIP hashes prove byte integrity, not archive authorship or confidentiality.
- Native packages remain unsigned community builds until platform code-signing identities are
  configured.

## Publication gates

1. Merge the reviewed preparation through protected `main` with every required check green.
2. Run the read-only native rehearsal for all six supported targets on the exact merge commit.
3. Review the 23-asset candidate, checksums, SBOMs and native lifecycle results.
4. Create the verified annotated `v1.9.0` tag with the authorized signing identity.
5. Let the tag workflow rebuild, attest, verify and publish the immutable release.
