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
| Revoke | Current account plus current password | The owned revoked `GrantView` |

Failed password checks are tracked in memory per account, rather than by the shared loopback
address. Five failures within 15 minutes pause new issuance for 15 minutes. Revocation still
verifies every submitted password during that interval, so a correct password can always revoke a
compromised grant and clears the failure state. Password verification is serialized per account,
so parallel requests cannot fan out expensive checks or pass a stale pre-lockout decision. Grant
creation refuses a thirty-third active grant. Listing returns all active grants before adding at
most 100 recent expired or revoked rows, so an active bearer cannot disappear from the management
surface.

An outer ASGI middleware marks every response below this path
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
4. route unmount clears the ref and destroys the component state;
5. no storage API, query string, URL, log or configuration snippet receives the bearer.

Creation moves focus to the one-time panel and announces only that the grant is ready, never the
bearer. Dismissal returns focus to the issuance button. Revocation is an inline, keyboard-operable
confirmation that asks for the password again; cancelling returns focus to that grant's revoke
button. Successful revocation moves focus to the new revoked status and announces the result.
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
| Browser or intermediary caching | Path-wide no-store middleware plus response contracts |
| Cross-user listing or revocation | User id is taken from the authenticated account and included in every query |
| Password or bearer in diagnostics | `SecretStr`, content-free errors, logging redaction and tests |
| Parallel password fan-out or blocked emergency revoke | Per-account serialized guard; correct-password revocation bypasses the issuance lock |
| Active grant hidden by recent history | Active-grant cap plus a list contract that always returns every active row |
| False zero while the register is unavailable | Unknown-state metric and disabled issuance until a successful list |
| Silent clipboard disclosure | Clipboard call exists only behind an explicit button |
| Broad default access | Initial selection contains only content-free `system:read` |
| Concurrent desktop and agent reads | Existing exclusive lease returns `vault_busy` |
| Configuration committed with a token | Displayed snippets contain only the environment-variable name |

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
- Operating-system credential-manager integration is documented rather than automated; adding it
  would require a separate native secret-storage boundary and platform release tests.
