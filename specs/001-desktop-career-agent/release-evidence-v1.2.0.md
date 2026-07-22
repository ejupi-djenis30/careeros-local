# CareerOS Local v1.2.0 release preparation

Date prepared: 2026-07-22

Status: local release-candidate implementation verified. No tag, draft, GitHub Release, attestation
or production deployment was created by this work.

Cross-artifact results: [application-readiness convergence](application-readiness-convergence.md)
and [v1.2 release convergence](release-convergence-v1.2.0.md).

## Candidate scope

v1.2.0 adds a deterministic Application Readiness Pack to the real desktop workflow. It evaluates
nine inspectable completeness checks, explains every result, exports canonical JSON or safe
Markdown with an exact SHA-256 header, and provides revision-safe repairs without recreating the
application. The seed and recorded product tour now create a published resume, link it to a detailed
application and display a real 100/100 preflight. Core behavior remains local and usable without a
model or network connection.

All seven authoritative version sources report `1.2.0`; the planned stable tag is `v1.2.0`. Release
date metadata is `2026-07-22`.

## Local verification recorded for this candidate

- Version contract: `python -m scripts.check_release_versions` passed with
  `RELEASE_VERSION=1.2.0 SOURCES=7`.
- Backend acceptance and coverage after the final audit delta: 1,046 passed, 4 expected skips;
  branch-aware coverage was 80.51%, above the 80% release threshold. The same clean run includes
  the artifact-byte verification paths and all 62 packaging/release tests.
- Application-focused checks: 29 application/seed tests and two OpenAPI contract tests passed in
  targeted runs before the earlier full suite. The final 18-test application API run additionally
  covered real PDF/DOCX files plus deleted, corrupt, path-escaping, unreadable and length-mismatched
  artifact records.
- Release/version policy: 67 tests passed, including ambiguous publication, sequencing, immutable
  assets, license, SBOM and seven-source version cases.
- Python static checks: Ruff passed for `backend`, `tests/backend`, `alembic/versions` and `scripts`;
  mypy passed for `backend` and `scripts` (200 source files in the broad local run).
- Frontend: the post-audit coverage run passed 54 files and 286 tests. V8 reported 74.20%
  statements and 79.66% lines; the final nine-test application detail/readiness/preparation run and
  ESLint also passed after preserving the create-flow opener. The production Vite build, three
  production-license tests and three transactional demo-publisher tests passed.
- Rust desktop shell: `cargo fmt --check`, locked Clippy with `-D warnings`, and locked tests passed
  (10 tests).
- Migrations: `upgrade head`, `downgrade -1`, and `upgrade head` passed against a fresh disposable
  SQLite vault. No migration was added for readiness because the report is derived and the existing
  application snapshot/event schema is sufficient.
- Performance: the final 10,000-record acceptance measured application-page p95 at 13.115 ms and
  profile-read p95 at 4.496 ms against a 200 ms budget (30 samples, 200-row page).
- Application-readiness performance: the exact command
  `$env:RUN_PERFORMANCE_TESTS='1'; .\.venv\Scripts\python.exe -m pytest tests/backend/performance/test_application_readiness_performance.py -q -s`
  passed with 300 selected confirmed facts, real verified PDF and DOCX artifacts, and a 17.805 ms
  p95 across 30 samples against the 100 ms budget.
- Supply chain: both hash-locked Python audits and npm's high-severity audit found no known
  vulnerabilities. Cargo audit passed with the repository's narrow `RUSTSEC-2024-0429` exception,
  reporting 16 allowed unmaintained warnings; Cargo license policy passed.
- Workflow policy: actionlint passed for every workflow.
- Privacy and repository hygiene: 31 focused security/identity tests passed and Trivy's current-tree
  high/critical secret scan exited cleanly. Public metadata contains no personal collaborator name,
  username or personal email; it uses collective credit and `info@ejupilabs.com`. The repository
  owner's GitHub slug remains only where required to route repository, Pages, release and support
  links.
- Real product proof: the disposable demo pipeline applied all migrations, seeded through public
  loopback APIs, started FastAPI and React, opened the seeded application in Chromium, waited for
  `.readiness-badge--ready`, and published an exact 40.000-second, 3.3 MiB WebM plus poster, GIF and
  screenshots. A second run completed cleanly after the Windows cleanup race was fixed. No other
  video file is present in the repository.
- Portfolio integrity: the local structure, links, assets and baseline accessibility validator
  passed after media publication.

## Evidence limits and required next steps

These are local implementation checks, not publication evidence. This run did not build or smoke
the six native installer targets and did not exercise hosted GitHub identities, attestations or
immutable release state.

Before publication:

1. Merge through protected `main` with every required check green on the exact merge commit.
2. Run and review the read-only six-platform native rehearsal from that commit.
3. Use the authorized verified signing identity to create the annotated `v1.2.0` tag.
4. Let the tag workflow rebuild, attest, verify and publish; do not create or alter the Release by
   hand.
