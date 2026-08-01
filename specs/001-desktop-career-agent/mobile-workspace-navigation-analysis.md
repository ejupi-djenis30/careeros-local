# Mobile workspace navigation isolation — analysis

Date: 2026-07-30

## Scope and upstream convergence

The starting branch contained the durable dossier implementation but diverged before the current
distribution line. `git log --left-right --cherry-pick HEAD...origin/main` showed the local dossier
commit patch-equivalent to its merged counterpart and ten newer commits only on `origin/main`.
Those commits contain the dossier contract stabilization, CV-first onboarding, mobile touch-target
work, Agent Access and the v1.10 distribution changes.

The clean worktree was advanced without merging, committing or staging by applying the exact
`HEAD..origin/main` content delta. A blob audit compared every file in the resulting tree against
`origin/main`: 923 files checked, zero missing and zero mismatches. The real Git index remained
empty. This preserves the dossier v6 schema and its later stabilization while making this review
operate on the current v1.10 code and gate definitions.

## Findings

1. The mobile sidebar visually behaved like a modal drawer, but the skip link and workspace stayed
   available to assistive technology, body scrolling was not locked, and the scrim was advertised
   as a keyboard target even though the drawer focus trap excluded it.
2. Escape and direct navigation closed the drawer, but a mobile-to-desktop resize could retain open
   state and stale scroll/focus cleanup.
3. The first modal-role implementation placed `role="dialog"` on an `aside`. The new axe assertion
   rejected that role/element pairing. A neutral container now exposes `dialog` only while open and
   `complementary` while it is the persistent desktop sidebar.
4. The production entrypoint imported the complete Bootstrap JavaScript bundle even though a
   repository-wide scan found no plugin constructors and no interactive `data-bs-toggle`,
   `data-bs-target`, `data-bs-dismiss`, `data-bs-ride` or `data-bs-spy` attributes. The unused file
   is 80,496 bytes raw and 23,879 bytes gzip.
5. After aligning the virtual environment to `requirements-dev.lock`, Ruff 0.16 classified the
   top-level `alembic` imports inconsistently after migration assets moved under
   `backend/migrations`. The required gate failed seven import blocks. Declaring `alembic` as an
   explicit third-party package fixes the classification without rewriting historical tests or
   migration bootstrapping.

## Implemented behavior

- Constitution 1.1.5, FR-084, SC-028, the plan and tasks now describe the same modal-navigation
  boundary.
- Opening the drawer makes the skip link and workspace inert and assistive-technology hidden,
  preserves and locks body overflow, focuses the first drawer control and wraps Tab in both
  directions.
- Escape, drawer route activation and reaching the existing 992 px desktop breakpoint close the
  drawer. Cleanup restores scrolling and focuses the connected opener; unmount performs the same
  cleanup.
- The scrim remains pointer-operable but is hidden from assistive technology and removed from the
  tab sequence because an explicit labelled close control is already inside the drawer.
- Existing reduced-motion CSS suppresses both transform and opacity transitions. A real Chromium
  harness verifies this and the 320, 375, 991 and 1,280 px layouts.
- Bootstrap CSS and the static `data-bs-theme="dark"` attribute remain; only the unused JavaScript
  runtime import was removed.

## Validation evidence

| Gate | Exact result |
| --- | --- |
| Focused shell tests | `npx vitest run src/app/WorkspaceShell.test.jsx src/components/Layout/Sidebar.test.jsx`: 2 files, 4 tests passed, including axe |
| Shell browser acceptance | `npm run test:shell-responsive`: 320, 375, 991 and 1,280 px geometry, overflow and reduced motion passed |
| Full frontend suite | `npm test`: 71 files and 399 tests passed; 3 frontend license-policy tests passed |
| Frontend lint | `npm run lint`: passed |
| Production build | `npm run build`: passed; Vite retained an informational 505.23 kB main-chunk warning |
| Existing agenda browser gate | `npm run test:agenda-responsive`: 4 viewport widths, contrast and DST passed |
| Existing Pages browser gate | `npm run test:pages`: 15 viewport widths passed |
| Frontend dependency audit | `npm audit --audit-level=moderate`: 0 vulnerabilities |
| Bootstrap runtime dependency scan | Repository scan returned `NO_BOOTSTRAP_RUNTIME_DEPENDENCIES` |
| Python lint | Ruff 0.16.0, `ruff check backend tests/backend`: passed after explicit Alembic classification |
| Python types | `mypy backend --ignore-missing-imports --no-error-summary`: passed |
| Complete backend suite | Locked environment, explicit OS `--basetemp`: 1,573 passed and 4 performance tests skipped by their opt-in marker |
| Performance budgets | `RUN_PERFORMANCE_TESTS=1 pytest tests/backend/performance -q`: 4 passed; 10k-read p95 values and readiness/canvas budgets passed |
| Rust gates | `cargo fmt --check`, Clippy with warnings denied and `cargo test`: passed; 17 tests |
| Migration round-trip | Isolated OS-temp SQLite database: upgrade to `e7f8a9b0c1d2`, downgrade to `d6e7f8a9b0c1`, re-upgrade passed |
| Patch hygiene | `git diff --check`: passed; real index contained 0 entries |
| Process cleanup | No Vite or Uvicorn process remained |

The initial pre-alignment backend run reached 100% but exited during Pytest temporary-symlink
cleanup with Windows `WinError 1463`; it is not counted as passing. Both complete reported backend
runs used explicit OS temporary bases, and the final locked run passed.

## Residual limits

- Vite still reports a 505.23 kB minified initial chunk. Removing the unused Bootstrap runtime
  reduced unnecessary startup code, but further splitting needs a separate measured loading plan.
- A packaged installer, signed release, platform matrix, frozen-sidecar smoke and live compact-model
  evaluation were not run in this local review. Existing release workflows remain authoritative.
- The worktree intentionally contains the uncommitted v1.10 alignment plus this hardening. No
  commit, merge, push, release or deployment was performed.
