# Durable application dossier drafts — cross-artifact analysis

Date: 2026-07-29

## Decision under review

CareerOS Local now keeps one mutable dossier working copy per Application in the local SQLite
vault. The draft is separate from immutable Application events, is bound to the exact Application
revision and linked Resume Version, and has its own monotonic compare-and-swap revision.

The dossier workspace restores and debounces the working copy without browser storage. Publication
first saves the visible form, verifies its publishable projection against that exact saved revision,
then deletes the draft only in the same transaction that advances the Application and records the
immutable dossier event. Existing API clients retain direct publication only while no saved draft
exists.

## Contract analysis

| Boundary | Implementation evidence | Result |
| --- | --- | --- |
| Local persistence | `application_dossier_drafts` has one row per Application, an owned Resume Version foreign key, positive revisions, timestamps and database cascades | Converged |
| Draft schema | Strict Pydantic contracts bound aggregate JSON, collections, strings and evidence links; stable row ids must be nonblank and unique within each collection | Converged |
| Save concurrency | Create and update acquire the SQLite writer transaction, re-read the current Application binding after the write starts and use draft compare-and-swap revisions | Converged |
| Delete concurrency | DELETE requires the expected draft revision and changes no row on a stale or missing comparison | Converged |
| Publication atomicity | A conditional delete matches draft id, draft revision, Application revision and Resume Version; any mismatch rolls back before the immutable event is committed | Converged |
| Ownership and transport | GET, PUT and DELETE resolve the authenticated user's Application; responses are private/no-store and mutation routes are rate-limited | Converged |
| Failure UX | Autosave states, retry, deliberate conflict rebase, discard and publication preserve the visible form through transport, validation and conflict failures | Converged |
| Browser boundary | Draft content is stored through the loopback API in SQLite and never in browser storage | Converged |
| Archive validity | Format v6 adds the draft table after its dependencies; preflight checks required ids and timestamps, revisions, content bounds, one row per Application and foreign keys before writes | Converged |
| Historical restore | Formats v1 through v5 decode with an empty draft table and remain inspectable and restorable | Converged |
| Erasure | Application deletion and complete vault erasure include the draft row, with database-enforced cascade behavior and accounting coverage | Converged |
| Migration | Alembic head `e7f8a9b0c1d2` creates the table, index, unique constraint, checks and cascading foreign keys; downgrade removes it cleanly | Converged |
| Public contract | Specification, plan, tasks, data model, OpenAPI 1.2.0, architecture, privacy, daily-driver and changelog describe the same bounded draft model | Converged |

## Adversarial review

The review found two transaction races in the initial implementation. Publication originally loaded
a draft and later deleted it by primary key, which could consume a newer concurrent autosave while
publishing older content. Saving also checked the Application binding only before the draft write,
which left a window for a changed Application or Resume Version to be accepted. The implementation
now conditionally consumes the exact loaded tuple and re-validates the Application binding after
the write has acquired SQLite's writer transaction. Regression tests force both interleavings and
prove rollback.

API tests cover unauthenticated and cross-user reads, private cache headers, create/update/delete
compare-and-swap behavior, stale Application and Resume bindings, duplicate and blank stable row
ids, schema and aggregate bounds, incomplete rows, failure rollback, exact-draft publication and
the no-draft compatibility path. Frontend tests cover restored content, debounced autosave, errors,
conflicts, discard, publication ordering and accessible status feedback.

Archive tests round-trip v6 drafts and restore v1 through v5. Adversarial archives with missing
required identifiers or timestamps, invalid content, broken relationships or duplicate
per-Application rows are rejected before database or managed-file mutation. Migration tests inspect
the exact columns, nullability, unique constraint and cascading foreign keys, then exercise
downgrade and re-upgrade.

## Verification result

- Backend: 1,483 passed and 4 expected skips. The final focused Application API rerun passed all
  45 tests.
- Frontend: 67 Vitest files and 357 tests passed. The frontend license inventory passed all 3
  checks; ESLint and the Vite production build passed.
- Rust: formatting and Clippy over all targets with warnings denied passed; all 17 library tests
  passed.
- Static and contracts: Ruff passed over backend, backend tests and migrations; mypy passed over
  backend; OpenAPI YAML parsed and exposed version 1.2.0 with the dossier-draft route.
- Migration: isolated SQLite `upgrade head`, `downgrade -1`, `upgrade head` passed.
- Hygiene: `git diff --check` passed.

The Vite build retains its existing advisory for a 514.17 kB main chunk. It does not prevent a
correct production build. Packaged-binary smoke tests and the cross-platform CI/release matrix were
not run locally.

## Residual boundaries

The draft model assumes CareerOS Local's single-user SQLite writer boundary; it is not a
multi-device synchronization protocol. A stale draft remains recoverable but must be explicitly
rebased after its Application or linked Resume Version changes. Existing clients can publish
without a draft only when no saved working copy exists.

Portable ZIPs remain unencrypted and unauthenticated. Their hashes prove byte integrity, not archive
authorship or confidentiality. Publication and restore remain bounded by the local vault lock,
transactional preflight and platform filesystem guarantees described in the architecture and
privacy documentation.

Dependency updates remain separate from the dossier-draft behavior. Release validation must run on
the exact integrated candidate, including its current dependency locks, rather than relying on an
earlier feature-branch snapshot.
