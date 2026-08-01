# Crash-recoverable vault lifecycle convergence

## Scope

This review aligns User Story 5 recovery scenarios, FR-090–FR-097, SC-033–SC-037 and constitution
version 1.2.0 with the lifecycle migration, purpose-bound authentication, activity gate, restore
journal, storage primitives, API contracts and owner documentation.

## Requirement mapping

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Four durable states and safe migration | Constrained/indexed User lifecycle plus restore fingerprint | Schema/check/index, ready backfill, downgrade refusal and round-trip tests |
| Pending-state authority isolation | Access purpose, maintenance login and normal/automation dependency guards | Ordinary-route, refresh, grant, wrong-operation and password recovery tests |
| Reset/login race closure | Owner-row serialization and completion-time family sweep | Stale-user issuance and injected late-family regressions |
| Recovery logout | Exact erasure-sentinel deletion and password replacement | Old bearer `401`, distinct replacement and successful erasure |
| One destructive writer | Maintenance mutex and writer-priority reader/writer gate | Exclusion, fairness, cancellation and quiescence tests |
| Responsive health | Static root, pure liveness and try-reader readiness | Blocked database/writer and managed-worker cases |
| Restart-durable restore | Redundant checksummed monotonic journal and owner staging | Hard-crash, same-ZIP retry, corrupt/torn copies and lost-ZIP erasure |
| Safe cleanup | Exclusive-reference query, durable unlink and SQLite sanitation | Cross-account shared file plus SQLite/WAL/SHM marker tests |
| Canonical restore identity | UUID validation and derived asset/photo/resume paths | Traversal, control, uppercase UUID and binding-alias matrix |
| Durable publication | fsynced staging/directories and Windows write-through replacement | Fault injection, actual replacement and stale-temp startup cleanup |
| Safe restored automation | Session/grant revocation and schedules restored disabled | Portability round-trip and authorization regressions |
| Bounded resources | Archive ceilings and upload limit-plus-one reads | Compressed, expanded, member, record and source-upload tests |

## Cross-artifact findings

- Constitution 1.2.0, specification FR-090–FR-097, Phase U and Phase 27 use the same state names,
  same-archive recovery rule, erasure escape hatch and clean-rollback invariant.
- The data model matches the Alembic state/fingerprint checks and records the journal as filesystem
  recovery metadata rather than portable vault content.
- Static OpenAPI 1.3.0 documents login `session_state`, reset, restore, erasure, liveness/readiness
  and structured pending failures under the existing `/api/v1` server. Runtime contract tests
  confirm every documented operation exists.
- Architecture and privacy guidance state the exact 128/256 MiB, 5,000-member and 100,000-record
  ceilings, plain-ZIP trust boundary, same-ZIP retry and lost-ZIP erasure path.
- Restore state clears only after success commits or `RestoreRolledBackError` proves complete file
  and SQLite cleanup. `RestoreCleanupPendingError` remains pending by design.
- Successful restore revokes account authority and leaves schedules disabled; it cannot silently
  resume network-capable work.
- Startup cleanup is intentionally narrower than erasure: it visits fixed managed namespaces and
  cannot remove a similarly named model/runtime temporary.

## Review resolution

The final adversarial review found and closed three lifecycle-critical gaps: rollback of a journal
path newly referenced by another account, logout of the already-revoked erasure sentinel and clean
rollback from a restart retry remaining trapped in `restore_pending`. It also confirmed the
reset/login race needed both a locked lifecycle re-read and a final family sweep. Each resolution
has a regression at the same service/API boundary; none relies only on documentation.

The final repository review also found one swallowed exception while shutdown updated active search
status. Shutdown now emits a registry-sealed, content-free `server_shutdown` diagnostic and still
cancels/joins tasks and stops the runtime. Its regression proves an exception containing a private
marker is observed without logging the marker or blocking teardown.

## Final validation

| Gate | Command or evidence | Result |
| --- | --- | --- |
| Backend final regression | `python -m pytest tests/backend -q --tb=short` | 1,791 passed; four opt-in performance cases across three modules skipped; zero failures in 816.99 s |
| Backend branch coverage | Full `pytest-cov` run before stale-fixture correction | 81.04%, above the required 80%; the later zero-coverage final run proves all corrected tests pass |
| Opt-in local performance budgets | `RUN_PERFORMANCE_TESTS=1 python -m pytest tests/backend/performance -q -s` | 4 passed in 7.60 s; readiness p95 16.975 ms/100 ms, 10k-record application page p95 34.358 ms/200 ms and agenda p95 77.636 ms/200 ms |
| Corrected scheduler/search lifecycle mocks | Three affected unit files | 102 passed; owner state is explicitly `ready` rather than a permissive production fallback |
| Shutdown observability/lifespan | `tests/backend/unit/test_api_main.py` | 23 passed, including sanitized failure and continued teardown |
| Journal and atomic storage | Restore-journal plus storage-fault files | 25 passed after final journal typing |
| Critical rollback and retry findings | Shared-reference and retry-from-pending regressions | 2 passed |
| Python lint | `ruff check backend tests/backend scripts` plus focused final-diff reruns | Passed |
| Python types | `mypy backend scripts --ignore-missing-imports --no-error-summary` plus final main/journal rerun | Passed |
| Node manifest preflight | Node 24.18.0 `--test scripts/check_node_version.test.mjs` | 4 passed; exact range and every executable npm script covered |
| Static/runtime OpenAPI | Contract suite plus YAML 1.3.0 parse | 5 passed; 24 static paths and 37 schemas parse |
| Alembic convergence | Fresh SQLite `upgrade head -> downgrade base -> upgrade head` | Passed at `a9b0c1d2e3f4`; 22/22 ORM tables and semantic fresh-head equivalence |
| Desktop lock and supply chain | Locked/offline metadata, format, Clippy, 19 tests, `cargo audit` and cargo-deny license policy after `event-listener` 5.4.2 | Only 5.4.2 resolves; after the valid scoped `glib` exception, zero vulnerabilities and 16 unmaintained transitive warnings remain; license policy passed |
| Frozen backend lifecycle | PyInstaller 6.21.0 x86_64 onedir build plus `test_packaged_lifecycle.py` | Passed in 12.74 s; ready endpoint reached, parent exit stopped the sidecar and no backend/parent process remained |
| Frozen runtime policy | `verify_sidecar_build._verify_runtime_tree` against the QA onedir payload | Passed across 1,002 files; required model/evaluation resources present and forbidden remote/legacy AI packages absent |
| Frozen export workflow | `scripts/smoke_packaged_backend.py` against the same onedir payload | Passed registration, profile write, hashed PDF/DOCX publication and a 38,690-byte verified backup; parent exit left no process behind |
| Patch hygiene | Scoped and repository `git diff --check` | Passed |

## Execution notes

The first coverage-bearing full run reached the 81.04% branch threshold and passed 1,774 tests, but
16 scheduler/search unit cases used incomplete MagicMock owners. The new production guard correctly
treated their undefined lifecycle as pending. Tests now model `User.vault_lifecycle_state=ready`
explicitly; the affected 102-test selection and the final complete 1,791-test suite passed. No
compatibility path was added for an unknown lifecycle state.

Mypy initially identified eight `dict[str, object]` ambiguities in the new journal. A typed payload
and decoded-journal contract removed the ambiguity; a compatibility regression also confirmed the
checksum helper still ignores an existing checksum field when rebuilding adversarial test copies.
The final journal/storage selection passed 25 tests.

The Windows Alembic executable shim was blocked by application-control policy, so the migration
gate used the equivalent reviewed environment through `python -m alembic` rather than skipping it.
The full backend collection skipped four cases across three performance modules because
`RUN_PERFORMANCE_TESTS` was unset. Packaged lifecycle coverage lives outside `tests/backend`; a
temporary PyInstaller onedir payload was built outside the repository and that exact desktop case
passed. No commit, push, release, deployment, Docker mutation or external service operation was
performed by this slice. The final pytest process exited and left no additional backend test
service.

## Release boundary

This local convergence does not create a commit, tag, release, deployment or external mutation.
The frozen x86_64 Windows backend lifecycle is verified locally; signed artifacts, protected-branch
CI and full Tauri installer smoke tests remain release controls.
The filesystem honors requested flush/write-through semantics only to the guarantees of the host
filesystem and controller, which is documented rather than overstated.
