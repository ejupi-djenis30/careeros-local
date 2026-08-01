# Agent Access center convergence

## Scope

This review aligns User Story 10 acceptance scenarios 9 and 10, FR-082, FR-083 and SC-027 with the
desktop grant-management implementation, owner documentation and the unchanged read-only MCP
boundary.

## Requirement mapping

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Authenticated list/create/revoke | Focused automation API router using the existing grant service | Backend API and OpenAPI contract tests |
| Current-password confirmation | Constant-work check plus serialized per-account failed-reauthentication guard and reduction-only lockout path | Correct, incorrect, parallel, password-oracle and emergency-revoke cases |
| Complete lifecycle register | Active-grant cap plus all-active/recent-history listing | More-than-100-history and active revocation cases |
| Bounded inactive retention | Lifecycle-transition ordering and owner-only batched mutation-time pruning | Old-grant revocation, issue pruning and cross-user preservation cases |
| One-time non-cacheable bearer | Digest-only service plus API-wide no-store middleware and outer exception headers | Token persistence, early-response, validation and 500 assertions |
| Transient renderer handling | Lazy Agent Access page, focused state controller and compensating late-response revocation | Explicit clipboard, manual fallback, focus, dismissal, pending navigation, unmount, storage and axe tests |
| Least-privilege scope choice | Fixed bilingual scope picker starting at `system:read` | Component interaction and schema-bound tests |
| Lifecycle and revocation | Active, expired and revoked rows with password-confirmed mutation | Service, UI and idempotent backend tests |
| Honest client setup | Token-free Codex and Claude Code examples | UI assertions and source-install documentation |
| Owner guidance | README, privacy model and daily-driver guide | Repository documentation review |
| Browser and proxy boundary | Exact CORS allowlist, private Compose backend and disabled Uvicorn proxy headers | Preflight/refresh, direct XFF and distribution-contract cases |
| Real-browser quality | Fresh production build in Chromium | EN/IT axe WCAG 2.2 AA, keyboard, 320/390/1440 px, error recovery and post-exit secret checks |

## Cross-artifact findings

- The OpenAPI paths, FastAPI router and frontend service use the same three endpoint shapes.
- Pydantic request bounds match the four fixed scopes and 1-to-365-day UI choices.
- Route output models never serialize the persisted token digest.
- Failed checks for one account do not consume a shared loopback-IP limit. Once issuance is
  locked, the desktop route performs no more password checks and can only revoke an owned grant.
  Parallel checks and revocations for one account are serialized.
- Every active grant remains visible even when more than 100 inactive records exist.
- A successful issue or first revocation retains only the owner's 100 newest lifecycle transitions;
  active and foreign-account rows remain untouched. Immediate revocation retries remain identical
  while the row is retained.
- The API-wide private-path middleware wraps Trusted Host, CORS and desktop-session early exits;
  the outer exception path applies the same policy to unexpected 500 responses.
- Validation errors cannot reflect malformed passwords or request-controlled field names.
- Natural printable Unicode client labels are normalized consistently across API and service.
- The desktop session remains separate from MCP authentication in code, diagrams and copy.
- Every user-visible string is present in both English and Italian catalogues.
- Responsive styles collapse the form, register and configuration cards without changing DOM
  order or hiding security disclosure.
- Loading and failure states never claim that zero grants exist, and creation cannot race an
  unfinished registry read.
- Normal navigation and sign-out wait for pending issuance. Forced sign-out marks that issuance
  abandoned and waits for its compensating revocation before invalidating the server session. A
  forced unmount cannot display a late bearer and still attempts the same cleanup.
- A failed Clipboard API call focuses and selects the read-only token field, and revoking a newly
  issued grant removes its still-visible bearer.
- The existing terminal flow remains documented as a fallback, not a competing source of truth.
- Portable export contains no automation row, digest, grant id, label or bearer. Restore revokes
  only the restored account's active grants, and complete erasure deletes only owned grant rows.
- Unknown CLI usernames take the same fixed dummy-bcrypt path as known usernames.
- Arbitrary localhost ports cannot read credentialed responses or submit cookie-mutating auth
  requests. Login, registration, refresh and logout reject unlisted supplied origins. Compose
  exposes only Nginx, and direct forwarded client headers cannot select the SlowAPI key.
- The closed mobile drawer is visibility-hidden, so keyboard entry reaches the skip link rather
  than off-screen navigation.

## Remaining constraints

Write tools, automatic credential storage, remote MCP transport, installer-level CLI packaging and
simultaneous desktop/agent vault access remain out of scope. None is implied by the management UI.

## Proportional validation

The integrated feature branch completed these release gates:

| Gate | Command | Result |
| --- | --- | --- |
| Backend regression and branch coverage | `python -m pytest tests/backend -q --tb=short --cov=backend --cov-branch --cov-fail-under=80 --cov-report=term:skip-covered --cov-report=xml` | 1,693 passed, 4 opt-in performance tests skipped; 81.49% branch coverage |
| Opt-in performance budgets | `RUN_PERFORMANCE_TESTS=1 python -m pytest tests/backend/performance -q` | All 4 opt-in tests passed |
| Agent Access backend contracts | `python -m pytest tests/backend/automation tests/backend/unit/test_api_main.py tests/backend/unit/test_private_path_middleware.py -q --tb=short` | 85 passed |
| Python lint | `python -m ruff check backend tests/backend scripts` | Passed |
| Python type check | `python -m mypy backend scripts --ignore-missing-imports --no-error-summary` | Passed |
| Frontend regression and coverage | `npm run test:coverage` | 74 files and 420 tests passed; 79.47% statements, 71.56% branches, 70.33% functions and 84.11% lines |
| Frontend production licenses | `npm run test:licenses` | 3 checks passed |
| Frontend lint | `npm run lint` | Passed |
| Frontend production build | `npm run build` | Passed all raw and gzip budgets |
| Frontend dependency audit | `npm audit --audit-level=high` | No HIGH or CRITICAL vulnerabilities |
| Python dependency audits | `pip-audit -r requirements.lock` and `pip-audit -r requirements-dev.lock` | No known vulnerabilities |
| Rust desktop gates | `cargo fmt --check`, `cargo clippy` and `cargo test` | Passed; 17 tests |
| Agenda viewport acceptance | `npm run test:agenda-responsive` | Four viewport widths, contrast and DST boundaries passed |
| Agent Access browser acceptance | `npm run test:agent-access-quality` | EN/IT WCAG, keyboard, lifecycle and secret checks passed at 320, 390 and 1,440 px |
| Login and session runtime | Production Chromium through the final Nginx and backend images | Register, logout, login, refresh and final logout returned 200; secure path-scoped cookie removed |
| Exact image vulnerability policy | Pinned Trivy 0.72.0 HIGH/CRITICAL scan of both final OCI indexes | Zero findings in backend Alpine/Python and frontend Alpine targets |
| Standalone service cleanup | Exact `careeros-final-*` resource inspection after verification | No QA container, image, network or volume remained |
| OpenAPI parse and path check | `python -c "<parse contracts/openapi.yaml and assert both Agent Access paths>"` | OpenAPI 3.1 parsed; list/create and revoke paths present |
| Credential-shape scan | `rg -n --hidden -g '!frontend/node_modules/**' -g '!frontend/dist/**' -g '!.git/**' "<credential patterns>" .` | No credential-shaped secrets found |
| Patch hygiene | `git diff --check` | Passed |

## Result

The local implementation is converged. Rebase, protected-branch checks and verified merge remain
release controls rather than implementation evidence.
