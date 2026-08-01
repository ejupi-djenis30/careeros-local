# Replay-detecting refresh-session convergence

## Scope

This review aligns User Story 1 acceptance scenario 7, FR-089, SC-032 and constitution version
1.1.8 with the stateful refresh implementation, migration, privacy guidance and renderer recovery
contract.

## Requirement mapping

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Complete required JWT claims | Type-specific decode contracts for access and refresh tokens | Missing, malformed, wrong-type and pre-migration claim cases |
| Digest-only single-use family | `AuthSession` plus SHA-256 JTI digest | Database inspection and raw-token/JTI absence checks |
| Atomic rotation and replay response | Account/family/digest compare-and-swap followed by family revocation on mismatch | Sequential replay and real two-connection SQLite race |
| Current-or-old-token logout | Signed account and family revocation independent of the current digest | Rotation followed by logout with the old token |
| Bounded persisted authority | Eight unique account slots with expired/revoked reclamation and retry | Nine-login cap and database uniqueness cases |
| Upgrade fail-closed behavior | Empty-table Alembic revision and required `sid` | Exact schema, cascade, downgrade/upgrade/head and old-token cookie clearing |
| Restore, export and erasure privacy | Owner-scoped revoke/delete and archive exclusion | Two-user restore/erasure and archive-content cases |
| Transaction failure safety | Rollback on issue, rotation and revocation errors | Injected commit-failure regressions |
| Terminal renderer recovery | Unauthorized event after a refreshed retry also returns `401` | Client regression plus complete frontend suite |
| Honest residual lifetime | Stateless access token remains bounded by configured expiry | Specification, privacy guide and default-config review |

## Cross-artifact findings

- The constitution, specification, plan, task list and data model use the same required claims,
  eight-family cap, replay response and access-token residual boundary.
- The FastAPI routes, auth-session service, SQLAlchemy model and Alembic revision agree on the
  account/family identity and digest-only storage contract.
- The OpenAPI contract exposes refresh and logout under the `/api/v1` server and describes
  single-use rotation, replay rejection and path-scoped cookies.
- Registration, login, refresh and logout continue to use the existing exact browser-origin
  boundary. Native and CLI callers without an Origin header remain supported.
- Restore and erasure mutate only owned authority. Portable archives contain career data, not live
  browser-session state.
- A refresh-family revoke does not overstate access-token termination: the documented default
  residual is 30 minutes, and signing-secret rotation is the immediate global invalidation path.
- A failed refreshed retry produces no private response and broadcasts the shared unauthorized
  event, keeping the renderer contract aligned with the backend state.
- Node 24.18.0 is the documented and tested frontend floor; the final frontend evidence records the
  exact ARM64 executable used.

## Proportional validation

| Gate | Command | Result |
| --- | --- | --- |
| Backend full regression | `python -m pytest tests/backend -q --tb=short` | 1,724 passed; four explicit opt-in performance cases skipped |
| Focused auth and replay regression | `python -m pytest tests/backend/unit/test_api_routes_edges.py tests/backend/unit/test_auth_service.py tests/backend/security/test_refresh_session_rotation.py tests/backend/security/test_browser_origin_boundary.py -q --tb=short` | 77 passed |
| Extended lifecycle and migration matrix | Focused auth, origin, migration, portability, erasure and release selection | 168 passed |
| Python lint and type check | `ruff check backend tests/backend scripts`; `mypy backend scripts --ignore-missing-imports --no-error-summary` | Passed |
| Frontend regression and coverage | Node 24.18.0 ARM64 `npm run test:coverage` | 74 files and 421 tests passed; 79.45% statements, 71.52% branches, 70.33% functions and 84.12% lines |
| Frontend lint and production build | Node 24.18.0 ARM64 `npm run lint`; `npm run build` | Passed, including bundle budgets |
| Browser acceptance | `npm run test:login-quality`; `npm run test:shell-responsive`; `npm run test:agent-access-quality` | Login at 390/1280/1440 px; shell at four widths; EN/IT WCAG, keyboard, lifecycle and secret-erasure checks at 320/390/1440 px passed |
| Rust desktop gates | `cargo fmt --check`; `cargo clippy --all-targets -- -D warnings`; `cargo test` | Passed; 17 tests |
| JavaScript dependency audit | Node 24.18.0 ARM64 `npm audit --audit-level=high` | Zero vulnerabilities |
| Python lock audits | `pip-audit --disable-pip --no-deps -r requirements.lock` and dev lock | No known vulnerabilities in either fully pinned lock |
| OpenAPI static parse | Parse OpenAPI 3.1 and assert refresh/logout paths below the `/api/v1` server | Passed; 18 paths |
| Patch hygiene | `git diff --check` | Passed |

## Execution notes

The first full backend run passed 1,722 tests and skipped four opt-in performance cases, but exposed
two stale edge tests that patched the removed stateless decoder. Both tests were updated to the
stateful rotation boundary; the focused 77-test rerun passed. The first authoritative frontend
coverage attempt used the correct runtime but hit a 120-second orchestration timeout during CPU
contention; the same gate passed in 104 seconds with an adequate timeout. An earlier diagnostic
frontend run under Node 24.16.0 also passed but is not counted as authoritative.

The project virtual environment's `pip-audit` entry point could not import one compiled helper, and
a first transient `uv` audit completed the production lock before Windows failed to remove its
temporary interpreter. Re-running pip-audit with its documented no-pip mode avoided temporary
environment creation and completed both fully pinned locks successfully.

No Docker container, image, network or volume was started, stopped or removed during this slice.
No commit, push, release or deployment was performed.

## Result

The refresh-session slice is locally converged. Its stateful authority, lifecycle integration,
renderer recovery, documentation and proportional release gates agree. Rebase, protected-branch
checks and verified merge remain release controls rather than local implementation evidence.
