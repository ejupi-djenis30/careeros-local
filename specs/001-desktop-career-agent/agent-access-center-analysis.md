# Agent Access center analysis

## Purpose

The source-installed CLI and MCP server already provide a useful read-only interface, but creating
and revoking a grant required a terminal. This slice makes that existing authority understandable
and manageable from the authenticated desktop. It does not add an MCP transport, a write tool, a
remote service or another credential type.

## Boundaries carried forward

- The four fixed scopes and `AutomationGrant` table remain canonical.
- `backend/automation/grants.py` still owns label normalization, token generation, digest storage,
  scope ordering, expiry, authentication and idempotent revocation.
- The desktop bearer authenticates only loopback management routes. MCP continues to require the
  separate `CAREEROS_MCP_TOKEN`.
- Every MCP call still reacquires the exclusive vault lease and checks the grant again.
- No route accepts prompts, paths, SQL, documents or arbitrary scope names.

## Management contract

The focused `/api/v1/automation/grants` router exposes three operations:

| Operation | Authentication | Returned data |
| --- | --- | --- |
| List | Current desktop account | Every active owned `GrantView` plus 100 recent inactive rows |
| Create | Current account plus current password | One `GrantView` and one bearer shown once |
| Revoke | Current account plus current password before lockout; authenticated desktop ownership during lockout | The owned revoked `GrantView` |

Failed password checks are tracked in memory per account, rather than by the shared loopback
address. Five failures within 15 minutes pause new issuance for 15 minutes. Revocation still
verifies the submitted password until that threshold is reached. Once locked, the route does not
inspect another password or mutate the failed-check state. The authenticated desktop session may
only revoke an owned grant, so it can remove exposed authority without creating a password oracle
or clearing the issuance lock. Password checks and revocations are serialized per account, so
parallel requests cannot fan out expensive checks or pass a stale lockout decision. Grant creation
refuses a thirty-third active grant. Listing returns all active grants before adding at most 100
recent expired or revoked rows, so an active bearer cannot disappear from the management surface.
Inactive rows are ordered by the revocation or expiry transition that removed authority, not by
their original issuance time. Every successful issue or first revocation trims only that owner's
inactive tail to the most recent 100 rows in 500-row batches. Active rows and other accounts are
excluded. A newly revoked old grant therefore remains visible; repeat revocation returns identical
metadata while that row remains in the disclosed retention window. If all 32 active rows expire
without another mutation, the local table can temporarily contain 132 inactive rows until the next
successful mutation performs the trim.

An outer ASGI middleware marks every response below `/api/v1`
`Cache-Control: no-store, max-age=0` and `Pragma: no-cache`, including authentication, validation,
Trusted Host and desktop-session failures. The focused route repeats those headers on successful
and domain-error responses. The global handlers repeat them for validation and unexpected 500
responses that sit outside Starlette's user-middleware layer. They also preserve explicit
`HTTPException` headers such as `WWW-Authenticate` and `Retry-After`.

The create response is the only contract that contains a bearer. The database receives its
SHA-256 digest from the existing service. List and revoke serialize only `GrantView`; they cannot
recover the original token. Passwords use `SecretStr`, never enter a service DTO and are cleared
from the renderer after each mutation attempt. Validation responses omit raw input and validator
context, while arbitrary extra-field locations are redacted; malformed secrets or
request-controlled field names are never reflected.

## Renderer lifecycle

The page is lazy-loaded behind the normal authenticated workspace shell. It starts with
`system:read` only, explains each additional scope and requires an explicit password entry.
The one-time bearer exists only in component state and an in-memory ref:

1. creation does not call the Clipboard API;
2. the user must choose **Copy token**;
3. dismissal clears both state and the ref;
4. normal links and sign-out wait while issuance is unresolved;
5. forced sign-out marks the pending result abandoned, waits for its compensating revocation and
   only then invalidates the authenticated server session;
6. if the page is forcibly unmounted and the response still arrives, the controller immediately
   attempts to revoke that new grant with the already submitted confirmation;
7. route unmount clears the ref and destroys the component state;
8. no storage API, query string, URL, log or configuration snippet receives the bearer.

Normal navigation and sign-out cover the renderer-controlled lifecycle, but no browser can
guarantee cleanup after operating-system termination or sudden process loss. A successful server
commit may therefore leave an active metadata row whose bearer was never shown. The page and owner
guide direct the user to reopen the register and revoke any grant whose token was not saved.

Creation moves focus to the one-time panel and announces only that the grant is ready, never the
bearer. A clipboard failure focuses and selects the read-only token field for manual copying.
Dismissal returns focus to the issuance button. Revocation is an inline, keyboard-operable
confirmation that asks for the password again; cancelling returns focus to that grant's revoke
button. Successful revocation moves focus to the new revoked status and announces the result. If
the revoked grant owns the still-visible one-time token, CareerOS clears that token before the
announcement.
Only one revocation can be in flight. A failed create or revoke keeps the non-secret form context
visible, clears the password and reports a bounded error. Creation stays disabled until the access
register loads successfully; while its state is unknown, the metric shows unavailable rather than
an incorrect zero. Loading failure leaves an explicit retry path.

## Client configuration

The page includes credential-free examples for Codex and Claude Code. The Codex block uses the
documented stdio `command`, `args` and `env_vars` fields. The Claude Code command registers the
same stdio process without embedding the token. Both require
`--acknowledge-agent-disclosure`. Copying either snippet is explicit and does not copy the bearer.

The examples remain honest about installation: the native desktop installer does not currently
place `careeros` on `PATH`. A reviewed source install or an absolute executable path is still
required.

## Threat review

| Threat | Control |
| --- | --- |
| Reusing a desktop JWT from an agent | CLI/MCP authentication accepts only the separate grant token |
| Recovering old tokens from the UI or API | Digest-only persistence and metadata-only listing |
| Browser or intermediary caching | API-wide no-store middleware plus response contracts |
| Cross-user listing or revocation | User id is taken from the authenticated account and included in every query |
| Password or bearer in diagnostics | `SecretStr`, content-free errors, logging redaction and tests |
| Parallel password fan-out or blocked emergency revoke | Per-account serialized guard; locked sessions inspect no more passwords and may only revoke owned grants |
| Active grant hidden by recent history | Active-grant cap plus a list contract that always returns every active row |
| Unbounded inactive history or stale ordering | Owner-only lifecycle ordering and bounded mutation-time pruning |
| False zero while the register is unavailable | Unknown-state metric and disabled issuance until a successful list |
| Silent clipboard disclosure | Clipboard call exists only behind an explicit button |
| Grant finishes after route exit | Normal exits are blocked while pending; a late result triggers best-effort owned revocation |
| Process dies after the server commits | Explicit reopen-and-revoke guidance; metadata remains visible until revoked |
| Broad default access | Initial selection contains only content-free `system:read` |
| Concurrent desktop and agent reads | Existing exclusive lease returns `vault_busy` |
| Configuration committed with a token | Displayed snippets contain only the environment-variable name |
| Credential theft or auth-cookie mutation from an unrelated localhost app | Exact credentialed CORS origins plus fail-closed Origin checks on login, registration, refresh and logout |
| Forged forwarded address bypasses rate limits | Backend is private behind Nginx and Uvicorn ignores proxy identity headers |

## Rejected alternatives

- **Persist the token so the desktop can show it later**: convenient, but creates plaintext
  credentials at rest and contradicts the existing CLI contract.
- **Use the desktop access token for MCP**: would widen every authenticated API route into the
  agent boundary.
- **Add grant write tools to MCP**: an agent must not grant itself more authority.
- **Automatically copy on creation**: clipboard history and managers are separate trust
  boundaries; copying must express user intent.
- **Embed the token in client configuration**: project files are routinely committed or shared.
- **Keep a second management database**: would split revocation truth and make restore/erasure
  behavior ambiguous.

## Known limits

- A grant can be managed in the desktop while it owns the vault, but an external tool call must
  wait until the desktop releases the lease.
- Source installation is still required before either client can launch the MCP command.
- CareerOS controls data only until an MCP result reaches the chosen client.
- The failed-reauthentication guard and active-issuance lock are process-local because CareerOS
  Local runs one sidecar. A future multi-worker service would require shared coordination.
- Hard process termination can prevent the renderer's compensating revocation. The completed grant
  remains in the owned register and must be revoked there before the client is connected.
- Operating-system credential-manager integration is documented rather than automated; adding it
  would require a separate native secret-storage boundary and platform release tests.

## Final verification evidence

The 2026-07-31 convergence run completed the full backend suite with 1,693 passing tests, four
performance tests skipped by their explicit `RUN_PERFORMANCE_TESTS=1` opt-in and 81.49% branch
coverage. Running those four performance tests separately with the opt-in enabled passed every
budget. The full frontend suite passed 420 tests across 74 files with 79.47% statement, 71.56%
branch, 70.33% function and 84.11% line coverage. Rust formatting, Clippy and all 17 Rust tests
also passed.

Fresh production Chromium exercised Agent Access accessibility and lifecycle behavior at 320,
390 and 1,440 px. A separate final runtime flow registered an account, signed out, signed back in,
restored the session through refresh and signed out again. The refresh cookie was `HttpOnly`,
`Secure`, `SameSite=Lax` and scoped to `/api/v1/auth`; no authentication cookie remained after the
final logout.

The exact final backend and frontend images were scanned with pinned Trivy 0.72.0 and contained
zero HIGH or CRITICAL findings. Their OCI image indexes were
`sha256:a5c9c31200308a63fb93dd1c5f86f82ae718eb48380c48aeb07a2661e9569e17`
and `sha256:82325b96fb08c44da4f58eb510942adb1eb940f1b88fd7d7e93a5e2ae313485e`.
After the runtime and browser checks, the standalone `careeros-final-*` containers, images,
network, volumes and scan cache were removed. The user's pre-existing CareerOS stack was not
modified.
