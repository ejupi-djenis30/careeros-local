# CareerOS Local v1.8.0 release preparation

Date prepared: 2026-07-26

Status: the local release candidate and independent P0/P1 reviews are complete. Protected-branch
CI, the native package rehearsal and signed-tag publication remain remote release gates.

Cross-artifact results:

- [Career Vault search analysis](career-vault-search-analysis.md)
- [Career Vault search convergence](career-vault-search-convergence.md)
- [Job Library and application pipeline analysis](job-library-application-pipeline-analysis.md)
- [Job Library and application pipeline convergence](job-library-application-pipeline-convergence.md)

## Candidate scope

v1.8.0 turns job search into a workflow that can be used repeatedly, not a one-off result screen.
Confirmed Career Vault facts are the default search source, while an uploaded CV remains an
explicit alternative. CareerOS records a bounded, contact-redacted source snapshot and a durable
completion receipt, so a later session can explain which search finished without retaining raw CV
text in lightweight profile responses.

The job catalog now records first seen, last seen and content revision independently from each
profile. A changed advert invalidates older normalization and analysis work. An advert is never
marked closed merely because a provider omitted it from a later response.

The Job Library and application pipeline now share one logical opportunity per user. Job cards
show the current application stage and open the same timeline after it has been created. The
database enforces this rule during concurrent requests, while portable archive format v5 keeps the
relationship intact and remains able to inspect and restore formats v1 through v4.

The home screen reads persisted product state and gives a new user a short path through Career
Vault, local-model readiness, the first completed search and the first tracked application. The
same controls and state are available in compact mobile layouts.

All seven authoritative version sources report `1.8.0`; the planned stable tag is `v1.8.0`.

## Local verification recorded for this candidate

- Version contract: `python -m scripts.check_release_versions --expected-tag v1.8.0
  --expected-release-date 2026-07-26` reports `RELEASE_VERSION=1.8.0 SOURCES=7`; the release
  metadata tests pass 6 tests.
- Backend: the complete isolated suite passes 1,456 tests with 4 expected skips. A separate
  300-test integration slice and the two cases investigated after a resource-contended run also
  pass.
- Migration regression: the Jobs API and migration slice passes 25 tests. A database built from
  the complete Alembic history upgrades from `c5d6e7f8a9b0` to the single head
  `d6e7f8a9b0c1`, downgrades one revision and upgrades again while retaining data, indexes,
  uniqueness, foreign keys and the database-managed `jobs.updated_at` value.
- Python static checks: Ruff passes for backend, tests, migrations and scripts. Mypy passes for
  backend and scripts with the same missing-import policy used by CI.
- Frontend: 354 Vitest checks and all 3 dependency-license checks pass. ESLint and the production
  Vite build pass.
- Rust: formatting and Clippy with warnings denied pass. All 17 Rust tests pass.
- Manual product path: a disposable, fully migrated database completed manual listing creation,
  Job Library rendering, prefilled application creation and the resulting tracked-state deep link.
- Responsive review: the workspace, Job Library and application pipeline were checked at desktop
  and 390-pixel mobile widths. Navigation, dialogs, primary actions and long content remained
  usable without horizontal overflow.
- Independent privacy and concurrency review found no unresolved P0/P1 issue. It reran the stale
  normalization guard, phone redaction and cross-user deletion checks.
- Hygiene: `git diff --check` passes and the candidate contains no runtime database, test scratch
  directory, credential or generated command log.

The packaged-binary smoke test and complete native matrix remain mandatory in the existing
allowed CI and release runners.

## Claims and boundaries

- Career Vault search snapshots contain only confirmed, non-archived facts from an explicit
  allowlist. Contact-like fields and detected phone numbers are removed before the snapshot is
  persisted.
- Local-model matching and normalization remain required-analysis workflows. They fail closed
  when the approved local runtime is unavailable; CareerOS does not substitute heuristic output
  or a cloud model.
- Search receipts are deliberately small and content-free. They record completion state and
  counts, not queries, CV content, model prompts or provider payloads.
- Provider omission is not evidence that a listing closed. CareerOS records observed changes but
  leaves closure as an explicit fact.
- Portable ZIPs are integrity-checked but are not encrypted and do not prove who created an
  archive.
- Native packages remain unsigned community builds until platform code-signing identities are
  configured. GitHub provenance is not a substitute for platform signing.

## Publication sequence

1. Merge the reviewed candidate through protected `main` with every required check green.
2. Run and inspect the read-only native package rehearsal on the exact merge commit.
3. Create the verified annotated `v1.8.0` tag with the authorized signing identity.
4. Let the tag workflow rebuild, attest, verify and publish the immutable release.
