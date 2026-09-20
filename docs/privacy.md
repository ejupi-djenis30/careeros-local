# Privacy

CareerOS Local is designed to minimize disclosure of highly sensitive career data.

## Stored locally

The app may store identity and contact data, work and education history, skills, languages, achievements, goals, preferences, source documents, profile photos, resume drafts and publications, job snapshots, application tasks, working dossier drafts and dossier versions, coach conversations, and redacted AI execution metadata. Dossier drafts are stored in the local SQLite vault rather than browser storage and are removed with their application or a complete-vault erasure. Model binaries and partial downloads are stored in separate app-managed directories.

## Not collected

The project contains no product telemetry, advertising identifiers, cloud AI integration, remote prompt logging, or analytics SDK. The application does not silently upload a profile or resume. Job-provider requests are user-initiated search operations and disclose only deterministic queries built from the explicit role, strategy and preferences. Provider planning never invokes the local model, and only v3 cache records marked `deterministic-explicit` can be reused.
Links opened from job, resume and application data require HTTPS; unencrypted HTTP is accepted only
for exact loopback hosts used by local runtimes.

The daily application agenda is calculated locally from the authenticated user's scalar role and
next-action projections. It does not read task-event or dossier bodies, contact a calendar service,
or invoke the local model.

## Local account sessions

Access and refresh JWTs carry explicit token types, issuance times and unique identifiers. Access
tokens without the `access` type are rejected. The browser refresh cookie is HTTP-only,
SameSite-limited and Secure in production; a successful refresh replaces it with a token carrying
a new identifier.
New passwords are never silently truncated: registration and login reject values beyond bcrypt's
72-byte UTF-8 boundary before hash work. If an explicit logout request cannot clear the HTTP-only
cookie, CareerOS immediately hides the private workspace, reports that the server session was not
ended and offers a retry; it does not expose the login form as though logout succeeded.
The refresh cookie is restricted to `/api/v1/auth`; upgrades also delete historical root-path
CareerOS cookies. Browser cookies are host-scoped rather than port-scoped, so another service on a
different port of the same loopback host can still receive a cookie if the browser is induced to
request that exact auth path. The narrow path and exact Origin mutation checks reduce exposure but
do not make localhost ports separate cookie principals. The native desktop additionally requires
its per-launch session header. Fully isolating the Docker/browser profile would require a
dedicated origin boundary or another server-bound session factor rather than another cookie flag.

Refresh JWTs are single-use members of a restart-durable session family. The database stores a
non-secret family id and the SHA-256 digest of only the current JTI, never the raw JWT or JTI. A
successful refresh atomically replaces that digest. Reusing an older token, including the loser of
a concurrent refresh race, revokes the family so the new token cannot continue. Logout revokes the
family even when the supplied signed token has already rotated. Each account has eight
database-unique session slots; a new login at capacity removes the oldest family. Portable backups
exclude these rows, restore revokes the restored account's rows and complete erasure removes them.

An upgrade cannot backfill previously stateless refresh tokens because CareerOS deliberately did
not persist them. Such a token lacks the required `sid`, is rejected and cleared, and the user signs
in again. Access and refresh tokens now carry the same non-secret `sid`. Every protected request
checks that `sid` and subject against a live, unexpired, non-revoked session row, in addition to the
access JWT's own expiry. After logout, replay detection, restore or erasure commits, later requests
from that family are rejected immediately; a request authorized before the commit may still finish.
CareerOS does not persist access JWTs, access JTIs or a per-token blacklist—the existing family row
is the only live authority. If a logout commit fails, all revocations roll back, the response is
`503`, refresh cookies are cleared to prevent automatic restoration after reload, and the renderer
keeps only its in-memory access bearer long enough to offer an explicit retry.

Reset, restore and complete erasure persist a recovery state before changing private data. While
that state is pending, ordinary access, refresh and automation grants are denied. After the user
re-enters the current password, CareerOS can issue a maintenance-only access token with no refresh
token; it works only for the matching recovery operation and cannot open the workspace. Logging
out invalidates even an erasure recovery token. A later correct-password login issues a new
recovery authority, rather than reviving the old bearer.

## Search profile snapshots

A new search uses the Career Vault by default unless the request contains a non-empty uploaded CV.
The app freezes a bounded local snapshot when the search history entry is created. That snapshot
contains the profile headline, summary, relevant job preferences, and only confirmed,
non-archived career facts. It excludes dedicated contact fields, birth date, nationality,
references, links, draft facts, and archived facts. Contact and private-field patterns embedded in
otherwise eligible prose are redacted. Telephone redaction covers bounded local and international
forms with spaces, parentheses, dots, slashes or hyphens, including `00` international prefixes.
Explicit guards preserve common years, date/time values, grouped counts and contextual metrics.

The history entry stores the snapshot itself so a later rerun is reproducible. Its non-sensitive
metadata records the source, Career Vault profile and revision, ordered included fact identifiers,
and a SHA-256 digest. Editing the Career Vault does not silently alter an existing search. Start a
new search to use the newer revision. Searches explicitly started from an uploaded CV retain that
CV snapshot and the same digest-based reproducibility contract.

## CLI and agent access

CareerOS has two deliberately separate MCP modes.

The installed desktop workspace keeps the native application open. A dedicated console launcher
connects over standard input/output to exact grant-authenticated loopback bridge routes. It never
receives the desktop session token and never opens SQLite. A private connection descriptor contains
only bounded version/process metadata and the current canonical loopback API address. It is written
atomically after backend readiness, removed conditionally on shutdown, and rejected if stale, linked,
insecure, malformed, oversized, non-loopback, or owned by a dead/reused process. The launcher rereads
it before operations, so a client can survive a normal desktop restart without persisting an
ephemeral port.

The preserved wheel-based mode is an offline read-only interface. It opens the SQLite vault with URI
`mode=ro`, verifies `PRAGMA query_only=ON` on every connection and participates in the exclusive
desktop vault lease. The desktop must be closed for those legacy calls. Its original
`system:read`, `career:read`, `resume:read`, and `applications:read` scopes and seven bounded
metadata/readiness tools are unchanged.

Workspace access adds two explicit scopes:

| Scope | Authority |
| --- | --- |
| `context:read` | List assigned work and read its frozen detailed facts, preferences and target evidence |
| `proposals:write` | Submit one strict, idempotent discover, analyze or materials proposal for review |

A full work request needs both scopes. A signed-in owner creates the grant in **Agent access** after
re-entering the current password and acknowledging that selected data can be disclosed to an
external client. The bearer is returned once in a `no-store` response and kept only in the current
renderer component until the user copies or dismisses it. CareerOS persists a SHA-256 digest, grant
identity, scope set, expiry and revocation state, never the raw token. The client configuration
contains no bearer; `CAREEROS_MCP_TOKEN` must be supplied by the environment that starts the client.

Every bridge operation revalidates the bearer, grant identity, account, scopes, expiry, revocation,
work ownership and current vault lifecycle. Owner JWTs and `X-CareerOS-Session` are not accepted as
agent authority. Only the exact bridge namespace bypasses the desktop-session middleware; loopback
peer, canonical Host, origin policy, method, route, body limit and `Cache-Control: no-store` checks
still apply. Restore removes live grant authority, and complete erasure deletes owned grant records.

The installed MCP server registers exactly six closed-world tools:

- status and bounded work-request listing;
- frozen work context with instructions, revisions, input digest and an untrusted-source warning;
- strict idempotent proposal submission and a content-free receipt/review state;
- immutable CV-template metadata.

Context is capped at 64 KiB and result input at 256 KiB, with lower row and field limits. Detailed
context contains only confirmed selected fact IDs, explicit preferences and owned target snapshots
chosen for the request. It omits account credentials, dedicated contact records, unrelated career
records, source file paths, artifact bytes, prompts, desktop tokens and storage paths. Submitted
source URLs/text are stored as untrusted data and are
never fetched merely because an agent returned them.

Proposal submission does not approve or publish anything. CareerOS validates the discriminated
schema, citations, fact membership, source quotations, score policy, current input revisions,
idempotency key and request state. Owner-only UI routes perform rejection or acceptance. MCP has no
tool for fact confirmation, proposal acceptance, CV/dossier publication, transmission, grant
management, backup/restore, erasure, arbitrary file access, SQL, shell execution or free-form
network search.

This local transport does not make the connected model private. Codex, Claude Code or another
client may include selected MCP context in a request to its own provider. Starting the server
therefore requires `--acknowledge-agent-disclosure`. Use the smallest useful context, a short grant
lifetime and the provider policy appropriate for that data. Keep `CAREEROS_MCP_TOKEN` in operating
system credential facilities; never store it in a repository, MCP configuration, project `.env`,
shell startup file or prompt. Revoke it after use.

Grant creation and revocation remain owner actions on the authenticated loopback API. Repeated
failed password checks pause new issuance. During that lockout an already authenticated owner may
reduce only their own authority by revoking an owned grant; the route does not inspect another
password, issue access, expose another account or clear the lockout. Stable error responses and
application diagnostics omit bearer values, submitted context and model output.

Credentialed browser access uses exact local origins; another process on a different localhost port
is not trusted. Every `/api/v1` response is `no-store`. Production disables Swagger UI, ReDoc and
the HTTP OpenAPI endpoint. The MCP process opens no listener and ignores proxy environment for its
loopback connection. CareerOS has no hosted-model API, telemetry or remote error reporting.

Renderer cleanup is best effort if the process or operating system terminates during grant
issuance. On the next launch, reopen **Agent access** and revoke any completed grant whose token
you did not save before connecting a client.

## Model context

The local model does not automatically receive the complete vault. Each task selects a bounded evidence set. Retrieved source text is treated as untrusted data, and generated claims must cite selected local identifiers. Execution audits store fingerprints, counts, validation codes, timing, and model identity—not prompts or generated text.

## Control and portability

Users can export a manifest-verified ZIP backup from one consistent database snapshot. Before
deleting anything, they can inspect any supported backup even when the vault contains data.
Inspection replays schemas, relationships, application projections, checksums, and managed-file
bindings without writing database rows or files. Its response contains only the archive version and
digest, creation time, record and byte counts, compatibility, current restore eligibility, and
stable verification or warning codes. It never returns archive paths, profile fields, document
text, prompts, model output, or user identifiers.

Archive format 7 includes owned work requests, proposal history, template selections, material
provenance, packet journals and the exact immutable schema 3 packet bytes. It excludes raw grant
tokens. Restore preserves historical evidence but makes work terminal/inactive, clears live grant
and proposal authority, and requires a newly issued grant before another external-agent session.
Versions 1 through 6 remain readable through their original bounded contracts.

Backup verification accepts at most 128 MiB of compressed input, 256 MiB after expansion, 5,000
members and 100,000 decoded records. These bounds protect the local process because verification
uses bounded in-memory archive structures. Source-document upload reads stop at the configured
file limit plus one byte. Parser failures return stable content-free messages; document text and
parser internals are not copied into diagnostics.

A valid backup is not automatically restorable into the current vault. Restore remains a separate
action, requires an empty vault, and rejects conflicting managed identifiers. Provider listings may
be shared only when their provider identity is stable. Manually captured listings use a one-way,
server-derived per-user namespace, ignore client-supplied manual ids, and are never merged across
users. Shared provider rows exclude user-specific discovery queries, while restore rejects private
or stale cross-user collisions instead of silently merging them.

The exact confirmation phrase erases profile, resume, search, match, application, workflow,
coaching, learned-preference, and AI-audit data plus app-owned files. SQLite secure deletion, WAL
checkpoints, and vacuuming reduce recoverable database remnants; user-scoped staged-file cleanup is
retryable if an operating-system error interrupts it. Managed model/runtime files can be removed in
the same operation. A shared provider listing is removed only when neither a Job nor an Application
owned by another user still references it; application-only tracking is therefore preserved across
account erasure. Backup files are not encrypted or authenticated by the application: checksums
detect accidental or malicious byte changes, but do not prove who created an archive. Store backups
in an encrypted location if confidentiality is required.

Restore recovery keeps only a checksummed list of app-managed paths, the archive SHA-256 and
owner-scoped temporary bytes under `.restore/user-{id}`. It does not journal profile records or
document contents. If CareerOS stops after publishing a file, retry with the same ZIP. A different
ZIP is rejected so it cannot take over the prior operation. If the original ZIP is unavailable,
choose complete erasure; it removes the pending account's exclusive published bytes and staging.
A file now referenced by another local account is preserved. Failed restore clears recovery state
only after exclusive files are durably removed and SQLite rollback remnants are sanitized.

In the desktop app, the native writer receives a bounded raw payload, the required export digest,
and a validated suggested filename. It opens the save dialog itself, so the selected destination
never crosses the webview boundary. The writer reserves a random `create_new` part sibling, flushes
and re-reads it, moves an existing destination to a distinct random rollback sibling, promotes the
verified file, and verifies the final bytes before cleanup. File data is flushed on every supported
desktop platform; the containing directory is also synchronized on Unix, where the standard
filesystem API supports it. Rename and directory-durability guarantees still depend on the
destination filesystem. If final verification fails, CareerOS verifies and restores the previous
file. A browser download can be checked before handoff, but CareerOS cannot inspect the browser's
eventual destination.

## Operating-system protections

The app inherits the current user account’s filesystem permissions. Enable full-disk encryption, lock the device, restrict backup access, and remove old installers or archives from shared folders. Uninstalling an application may not remove user data on every platform; use in-app erasure first when disposal is intended.
