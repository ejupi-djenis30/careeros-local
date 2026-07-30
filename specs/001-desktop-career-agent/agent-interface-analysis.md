# Agent interface analysis

## Purpose

CareerOS needs to work from a terminal and from coding agents without turning the Career Vault
into a general-purpose data source. This review covers the source-installed `careeros` command,
the MCP stdio server and their shared read facade. The later authenticated desktop management
surface is reviewed in
[`agent-access-center-analysis.md`](agent-access-center-analysis.md). Neither slice adds remote
inference or makes the native installer provide a system command.

## Existing boundaries to preserve

- The SQLite vault and local artifacts remain canonical.
- `desktop_instance_lease` permits one vault-owning process at a time.
- The desktop sidecar uses an ephemeral session secret that belongs to one Tauri launch.
- Domain ownership checks are performed with the authenticated local user id.
- Local analysis remains fail-closed and uses the managed loopback model only.
- Logs and public errors exclude private content, prompts, tokens and paths.

Reusing the desktop token would couple automation to a running UI and create an unnecessary route
into every HTTP endpoint. Giving an agent the SQLite file, a filesystem root or a generic query
tool would bypass domain ownership and output contracts. A second HTTP server would add a listener,
port policy and network authentication surface for a use case that already has a parent process.

## Chosen boundary

The CLI and MCP entry points share `AutomationFacade`. Bootstrap happens before database imports:
the process resolves the CareerOS application-data directory, reads the existing installation
secret, points SQLAlchemy at the vault, checks the Alembic revision and acquires the desktop
instance lease. A CLI command holds it for that operation. MCP holds it during bootstrap, releases
it while idle and reacquires it before every tool call.

Authorization is a separate interactive step. The CLI asks for the CareerOS username and password.
The authenticated desktop can instead use the current account id and requires the password again
for create and revoke. A grant binds one user id to a label, expiry and fixed scope set. CareerOS
generates a high-entropy bearer token, returns it once and stores only its SHA-256 digest. Restore
revokes active grants; complete erasure deletes grant rows.

The initial scope set is deliberately small:

| Scope | Permitted reads |
| --- | --- |
| `system:read` | Product/schema status and local-model readiness |
| `career:read` | Profile presence, revision, completeness, issue count and fact counts |
| `resume:read` | Bounded draft and published-version metadata |
| `applications:read` | Bounded application summaries, deterministic readiness and next-action agenda |

The facade enforces scope on every operation. MCP tool discovery also filters the registered tools,
but that client-facing filtering is not the security control.

## Data minimization

The interface returns enough structure for an agent to answer questions such as “which application
needs attention?” or “is the local model ready?” It does not return:

- source-document or resume bodies;
- contact fields, application routes or artifact bytes;
- Career Vault fact prose or model prompts;
- access tokens, installation secrets or local storage paths;
- raw event, dossier or job-snapshot payloads.

Application rows still contain private metadata such as role, company, location, stage and next
action. Resume rows contain titles and version names. These fields are useful to the requested
workflow and must be treated as disclosed to the connected client. List limits, agenda horizons,
identifier lengths and timezone offsets are bounded by typed contracts.

## Transport and disclosure

MCP runs over stdio only. CareerOS opens no listener and makes no provider request. The connected
client can nevertheless include a tool result in a remote model request. The server therefore
refuses to start without `--acknowledge-agent-disclosure`, and the setup guide tells users to check
the client/provider policy, select the smallest useful scopes and keep the token out of prompts and
repository files.

## Failure behavior

| Condition | Result |
| --- | --- |
| Desktop app already owns the lease | `vault_busy`; no database session is opened |
| Vault or installation secret missing | Stable setup error without traceback or secret |
| Schema behind current head during a read | `migration_required`; no implicit migration |
| Explicit authorization against an old vault | Migration runs under the exclusive lease |
| Missing, malformed or unknown token | `grant_required` or `invalid_grant` |
| Expired or revoked token | `expired_grant` or `revoked_grant` |
| Tool outside the scope | Not registered in MCP; direct facade use returns `scope_denied` |
| Unexpected domain failure | Content-free `internal_error` or a stable mapped error |

## Rejected alternatives

- **Expose the desktop loopback API to agents**: too broad and tied to a transient desktop token.
- **Add HTTP or SSE MCP transport**: unnecessary listener and authentication surface for local
  parent-child use.
- **Give the agent a database, file or prompt tool**: cannot guarantee ownership, bounded output
  or read-only behavior.
- **Allow a desktop operation and MCP read at the same instant**: violates the established
  single-writer contract. An idle MCP process is safe because it does not own the lease.
- **Store the bearer token for convenience**: turns a vault read into reusable plaintext
  credentials at rest.
- **Add write tools in the first interface**: agent confirmation UX, idempotency and rollback need
  a separate specification; read access should not imply that authority.

## Known limits

- The CLI is installed from a source checkout and reviewed lock, not by the desktop installer.
- MCP tool calls fail with `vault_busy` while the desktop owns the vault. The idle MCP process may
  remain connected and retry after the desktop closes.
- Revocation and expiry are checked again before every tool call. If the grant identity or scope
  set no longer matches the session established at bootstrap, the user must start a new session.
- CareerOS cannot enforce how an external client stores or transmits a result after receiving it
  over stdio.
