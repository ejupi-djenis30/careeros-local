# CareerOS Local v1.3.0 release preparation

Date prepared: 2026-07-22

Status: local release-candidate implementation verified. No commit, tag, draft, GitHub Release,
attestation or production deployment was created by this work.

Cross-artifact result: [v1.3 release convergence](release-convergence-v1.3.0.md).

## Candidate scope

v1.3.0 turns the daily-driver path into a deterministic local workflow. Provider queries come only
from explicit roles, keywords and search preferences. Applications have bounded board projections,
typed next actions, calendar exports and versioned evidence dossiers. Portable archives restore
historical application rows by replaying their snapshots and events, while current v3 projections
must match that canonical replay before the transaction can commit.

The React workspace exposes loading, empty and transport-error states separately. In particular, a
failed resume-metadata or Career Vault request can no longer appear as an empty evidence set. The
demo uses the entirely fictional Mira Vale workspace and is recorded from the running application,
not from its presentation site.

All seven authoritative version sources report `1.3.0`; the planned stable tag is `v1.3.0`. Release
date metadata is `2026-07-22`.

## Local verification recorded for this candidate

- Version contract: `python -m scripts.check_release_versions` passed with
  `RELEASE_VERSION=1.3.0 SOURCES=7`.
- Backend acceptance and coverage: 1,090 passed with 4 expected skips. Branch-aware coverage was
  80.76%, above the 80% release threshold.
- Focused portability and release contracts: 86 tests passed, including projection-free v1, v2 and
  v3 restores, complete modern-v3 validation, rollback on inconsistent projections and exact
  re-export behavior.
- Python static checks: Ruff passed for `backend`, `tests/backend`, `alembic/versions` and `scripts`;
  mypy passed for `backend` and `scripts`.
- Frontend: 58 files and 300 tests passed. V8 reported 80.19% line coverage; the three deterministic
  production-license tests also passed. ESLint and the production Vite build completed cleanly.
- Rust desktop shell: `cargo fmt --check`, locked Clippy with `-D warnings`, and locked tests passed
  (10 tests).
- Migrations: `upgrade head`, `downgrade -1`, and `upgrade head` passed against a fresh disposable
  SQLite vault including the application next-action projection migration.
- Performance: every opt-in gate passed. Application readiness measured 22.744 ms p95 against a
  100 ms budget with 300 selected facts and verified PDF/DOCX artifacts. The 10,000-record gate
  measured profile reads at 4.993 ms p95 and the 200-row application page at 32.629 ms p95 against
  a 200 ms budget. Both resume-canvas budgets passed in the same four-test run.
- CI contract: the backend workflow now runs `tests/backend/performance` with
  `RUN_PERFORMANCE_TESTS=1`, so none of the three opt-in performance modules is omitted.
- Real product proof: the deterministic recorder applied every migration, seeded through public
  loopback APIs and exercised the React/FastAPI/SQLite application in Chromium. It published a
  3.3 MiB WebM plus GIF, poster and four screenshots after checking browser, console and API errors.
- Identity hygiene: the current tree contains no historical-person demo fixtures. Public demo data
  uses the documented fictional Mira Vale identity and `example.test` contact values.
- Presentation integrity: the portfolio validator passed local structure, links, assets and its
  baseline accessibility checks after media publication.

## Evidence limits and required next steps

These are local implementation checks, not publication evidence. This run did not build or smoke
the six native installer targets and did not exercise hosted GitHub identities, attestations or
immutable release state.

Before publication:

1. Commit the reviewed candidate intentionally and merge it through protected `main` with every
   required check green on the exact merge commit.
2. Run and review the read-only six-platform native rehearsal from that commit.
3. Use the authorized verified signing identity to create the annotated `v1.3.0` tag.
4. Let the tag workflow rebuild, attest, verify and publish; do not create or alter the Release by
   hand.
