# Agent Access center convergence

## Scope

This review aligns User Story 10 acceptance scenarios 9 and 10, FR-082, FR-083 and SC-027 with the
desktop grant-management implementation, owner documentation and the unchanged read-only MCP
boundary.

## Requirement mapping

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Authenticated list/create/revoke | Focused automation API router using the existing grant service | Backend API and OpenAPI contract tests |
| Current-password confirmation | Constant-work check plus serialized per-account failed-reauthentication guard | Correct, incorrect, parallel, lockout and emergency-revoke cases |
| Complete lifecycle register | Active-grant cap plus all-active/recent-history listing | More-than-100-history and active revocation cases |
| One-time non-cacheable bearer | Digest-only service plus path-wide no-store middleware and outer exception headers | Token persistence, early-response, validation and 500 assertions |
| Transient renderer handling | Lazy Agent Access page and focused state controller | Explicit clipboard, focus, dismissal, unmount, storage and axe tests |
| Least-privilege scope choice | Fixed bilingual scope picker starting at `system:read` | Component interaction and schema-bound tests |
| Lifecycle and revocation | Active, expired and revoked rows with password-confirmed mutation | Service, UI and idempotent backend tests |
| Honest client setup | Token-free Codex and Claude Code examples | UI assertions and source-install documentation |
| Owner guidance | README, privacy model and daily-driver guide | Repository documentation review |

## Cross-artifact findings

- The OpenAPI paths, FastAPI router and frontend service use the same three endpoint shapes.
- Pydantic request bounds match the four fixed scopes and 1-to-365-day UI choices.
- Route output models never serialize the persisted token digest.
- Failed checks for one account do not consume a shared loopback-IP limit, and a correct password
  can revoke access while issuance is locked. Parallel checks for one account are serialized.
- Every active grant remains visible even when more than 100 inactive records exist.
- The private-path middleware wraps Trusted Host and desktop-session early exits; the outer
  exception path applies the same policy to unexpected 500 responses.
- Validation errors cannot reflect malformed passwords or request-controlled field names.
- Natural printable Unicode client labels are normalized consistently across API and service.
- The desktop session remains separate from MCP authentication in code, diagrams and copy.
- Every user-visible string is present in both English and Italian catalogues.
- Responsive styles collapse the form, register and configuration cards without changing DOM
  order or hiding security disclosure.
- Loading and failure states never claim that zero grants exist, and creation cannot race an
  unfinished registry read.
- The existing terminal flow remains documented as a fallback, not a competing source of truth.
- Restore and erasure behavior remain owned by the original automation grant persistence path.

## Remaining constraints

Write tools, automatic credential storage, remote MCP transport, installer-level CLI packaging and
simultaneous desktop/agent vault access remain out of scope. None is implied by the management UI.

## Proportional validation

The integrated feature branch completed these release gates:

| Gate | Command | Result |
| --- | --- | --- |
| Backend regression and branch coverage | `python -m pytest tests/backend -q --tb=short --cov=backend --cov-branch --cov-fail-under=80 --cov-report=term:skip-covered --cov-report=xml` | 1,525 passed, 4 skipped; 81.40% branch coverage |
| Agent Access backend contracts | `python -m pytest tests/backend/automation tests/backend/unit/test_api_main.py tests/backend/unit/test_private_path_middleware.py -q --tb=short` | 85 passed |
| Python lint | `python -m ruff check backend tests/backend alembic/versions scripts` | Passed |
| Python type check | `python -m mypy backend scripts --ignore-missing-imports --no-error-summary` | Passed |
| Frontend regression and coverage | `npm run test:coverage` | 70 files and 377 tests passed; 78.64% statements, 70.60% branches, 69.25% functions and 83.44% lines |
| Frontend production licenses | `npm run test:licenses` | 3 checks passed |
| Frontend lint | `npm run lint` | Passed |
| Frontend production build | `npm run build` | Passed |
| Frontend dependency audit | `npm audit --audit-level=moderate` | 0 vulnerabilities |
| Agenda viewport acceptance | `npm run test:agenda-responsive` | Four viewport widths, contrast and DST boundaries passed |
| OpenAPI parse and path check | `python -c "<parse contracts/openapi.yaml and assert both Agent Access paths>"` | OpenAPI 3.1 parsed; list/create and revoke paths present |
| Credential-shape scan | `rg -n --hidden -g '!frontend/node_modules/**' -g '!frontend/dist/**' -g '!.git/**' "<credential patterns>" .` | No credential-shaped secrets found |
| Patch hygiene | `git diff --check` | Passed |

## Result

The local implementation is converged. Rebase, protected-branch checks and verified merge remain
release controls rather than implementation evidence.
