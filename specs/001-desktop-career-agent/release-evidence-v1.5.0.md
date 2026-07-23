# CareerOS Local v1.5.0 release preparation

Date prepared: 2026-07-23

Status: local release-candidate implementation verified. Protected-branch CI, native rehearsal and
the signed-tag publication workflow remain the remote release gates.

Cross-artifact result: [daily agenda convergence](daily-agenda-convergence.md).

## Candidate scope

v1.5.0 adds a private daily action agenda to the application workspace. It turns the existing
next-action projection into a bounded queue for overdue, today, upcoming, unscheduled and
needs-action work. Ordering is deterministic, every row belongs to the authenticated local user,
and omitted totals remain visible when the seven-day horizon or compact row limit is reached.

The agenda reads scalar application projections only. It does not replay private events or load job
snapshots, dossiers, model prompts or generated documents. Rows and totals share one SQL-statement
snapshot. The browser supplies a validated local-day boundary and refreshes at the next deadline or
midnight, including both Zurich daylight-saving transitions.

All seven authoritative version sources report `1.5.0`; the planned stable tag is `v1.5.0`.

## Local verification recorded for this candidate

- Version contract: `python scripts/check_release_versions.py --expected-tag v1.5.0` passes with
  `RELEASE_VERSION=1.5.0 SOURCES=7`.
- Backend acceptance: 1,274 passed with 4 expected performance skips. Branch-aware coverage was
  80.73%, above the 80% release threshold.
- Python static checks: Ruff passed for backend, tests, migrations and scripts; mypy passed for
  backend and release scripts.
- Frontend: 64 files and 330 tests passed with 81.31% line coverage. ESLint, the production Vite
  build and deterministic production-license audit passed.
- Agenda browser acceptance: Chromium passed at 320, 375, 768 and 1280 px, with no horizontal
  overflow or overlapping controls, AA text contrast and both Zurich DST boundary cases.
- Rust desktop shell: formatting, locked Clippy with warnings denied and all 10 unit tests passed.
- Migrations: `upgrade head`, `downgrade -1` and `upgrade head` passed against a fresh disposable
  SQLite vault.
- Performance: the single-statement agenda query measured 68.670 ms p95 over 10,000 applications
  against a 200 ms budget. Regression tests bind its projection-only SQL shape and covering-index
  availability without assuming that SQLite must choose an index for a two-row fixture.
- API contract: OpenAPI 1.1.2 parses and documents the bounded agenda request, response and typed
  validation failure.
- Privacy and concurrency: tests cover user isolation, a writer interleaved between count and row
  reads, stale-request cancellation and payload exclusion.

## Publication sequence

1. Merge the reviewed candidate through protected `main` with every required check green.
2. Review the read-only six-target native matrix rehearsal on the exact merge commit.
3. Create the verified annotated `v1.5.0` tag with the authorized signing identity.
4. Let the tag workflow build, attest, verify and publish the immutable release; do not alter it
   manually.
