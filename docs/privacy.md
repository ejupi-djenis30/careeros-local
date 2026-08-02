# Privacy

CareerOS Local is designed to minimize disclosure of highly sensitive career data.

## Stored locally

The app may store identity and contact data, work and education history, skills, languages,
achievements, goals, preferences, source documents, profile photos, resume drafts and publications,
job snapshots, declarative provider settings and confidential headers, application tasks, working
dossier drafts and dossier versions, coach conversations, and redacted AI execution metadata.
Dossier drafts and provider declarations are stored in the local SQLite vault rather than browser
storage and are removed with their owner or a complete-vault erasure. Model binaries and partial
downloads are stored in separate app-managed directories.

## Not collected

The project contains no product telemetry, advertising identifiers, cloud AI integration, remote
prompt logging, or analytics SDK. The application does not silently upload a profile or resume.
Job-provider requests are user-initiated search operations and disclose only deterministic queries
built from the explicit role, strategy and preferences. Custom providers are non-executable
declarations restricted to their public HTTPS origin, and disabled until explicitly enabled.
Provider planning never invokes the local model, and only v3 cache records marked
`deterministic-explicit` can be reused.
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

The separately installed `careeros` CLI and its MCP server use a distinct, scoped automation
boundary. The Python wheel is separate from the desktop installer. A signed-in user can issue and
revoke grants from the desktop **Agent access** page after re-entering the current CareerOS
password. The CLI provides the same authorization path for terminal workflows. A grant belongs to
one local account and has a label, an expiry and one or more granular read, write or execution
scopes across system status, Career Vault, resumes, jobs, search, providers and applications. The
bearer token is displayed
only when the grant is created. The response is marked `no-store`, the renderer keeps the bearer
only in the current component, and copying requires an explicit button press. Dismissal or
navigation removes the visible bearer; it never enters browser storage. CareerOS stores its
SHA-256 digest, not the original token. The authenticated page lists only owned grant metadata.
Creating or revoking a grant requires another password check.
The portable backup format intentionally excludes automation-grant rows, including their labels,
scope metadata and token digests. Complete vault erasure deletes the owned rows instead. Successful
grant mutations retain only the 100 most recent inactive lifecycle transitions for that account;
active grants are always kept and another account is never pruned.
Portable provider declarations omit every configured header and are restored disabled. The owner
must inspect and explicitly re-enable each imported source, supplying any credentials again.

MCP opens a fresh session only while it holds the exclusive desktop vault lease. Typed mutations
reuse the same owner filters, compare-and-swap revisions, evidence validation and local-model
readiness gates as the desktop. Grant authorization and revocation use a separate,
password-confirmed path; neither operation is available through the MCP tool surface.

The MCP server communicates over the parent process's standard input and output and opens no
network listener. Ordinary Vault operations generate no outbound or cloud traffic.
`run_job_search` and `test_provider_configuration` are explicit open-world operations and contact
only enabled, declared public HTTPS job origins. The `get_local_model_status` tool may make a
content-free HTTP readiness probe to the configured, allowlisted local-runtime
endpoint. That endpoint is loopback by default; container deployments may explicitly allow a
single-label runtime alias such as `ollama` or `host.docker.internal`. The probe contains no Career
Vault data or prompt, does not contact a cloud-model provider and does not start a job search. The
tools expose bounded projections:

- product, schema and local-model readiness;
- the complete structured Career Vault when `career:read` is granted;
- resume drafts and versions needed to generate, revise and publish truthful local materials;
- jobs with receipt-verified local analysis and explicit source identity;
- provider declarations with every configured header value redacted;
- application history, deterministic readiness, dossier drafts and a bounded next-action agenda.

The tools do not accept arbitrary paths, files, SQL or prompts. They do not expose source-document
bytes, artifact bytes, local storage paths, access tokens, provider-header values or model prompts.
User-authored profile, resume, job and application content can contain personal or sensitive text;
authorizing its scope allows the connected agent to receive it. Typed create, update and narrowly
targeted delete tools exist for ordinary product workflows. Backup/restore, complete-vault erasure,
grant management, model installation and arbitrary data access remain desktop/operator-only.

This boundary does not make an external agent private. An agent can include MCP results in a
request to its own provider. Starting the server therefore requires the explicit
`--acknowledge-agent-disclosure` flag. Issue the smallest useful scope set and short lifetime,
protect `CAREEROS_MCP_TOKEN` with the operating system's credential facilities, and revoke the
grant after use. Never store the bearer token in a repository, MCP configuration, project `.env`
or shell startup file, and never paste it into a prompt.

Grant management uses the authenticated loopback desktop API, but the desktop access token is
never accepted as an MCP credential. The management API returns no resume, application or Career
Vault content. It tracks failed password checks per account and can pause new grant creation after
repeated failures. Once locked, the revoke route stops inspecting passwords and lets the already
authenticated desktop session perform only an owned-grant revocation. It cannot issue access,
inspect another account's grants or clear the lockout. Stable errors and later list responses
contain no bearer or password.

Credentialed browser access uses exact local origins; an unrelated app on another localhost port
is not trusted. Login, registration, refresh and logout reject any supplied browser origin that is
not in that exact allowlist; native and CLI requests without an `Origin` header remain supported.
Every `/api/v1` response is marked `no-store` by the backend even when the desktop connects
directly. In the container profile only Nginx is published to the host, the backend remains on the
private Compose network, and backend runtimes ignore forwarded client-identity headers. Container
access logs retain status, method and request duration only: they do not record client addresses,
paths, query strings or resource identifiers. Structured application diagnostics remain
content-free and available for failures.
The API does not use dynamic response compression, avoiding a length oracle across authenticated
content. The web proxy gzips public fingerprinted assets only. It revalidates the SPA shell and
unhashed public files on every rollout and gives a long immutable lifetime only to hash-named
build assets.

Production runtimes do not publish Swagger UI, ReDoc or the HTTP OpenAPI endpoint. This prevents
developer documentation pages from loading CDN assets and removes an unnecessary production
surface. The schema remains generated directly in Python for contract and CI validation.

Each CLI command and MCP tool call uses the same exclusive vault lease as the desktop sidecar.
MCP releases it after bootstrap and after every call, so an idle server does not keep the desktop
closed. Before each tool operation, it reacquires the lease and revalidates the token, expiry, revocation
state and original grant identity. A call made while CareerOS Local owns the vault returns
`vault_busy`; it does not become a second writer. Restore revokes all active automation grants for
the restored account, and complete vault erasure deletes the grant records.

Renderer cleanup is best effort if the whole process or operating system terminates during
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

A new Vault contains no network job providers. Configured providers and imported pack entries are
owned rows and are contacted only while their current revision is enabled. Provider and pack JSON
is strictly bounded data, cannot name executable modules or paths, and cannot carry configured
headers. The bundled Swiss manifest is discoverable but not installed automatically. Portable
archives preserve provider and pack provenance, omit configured headers, and force every restored
provider back to disabled so importing a backup cannot silently grant network access.

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
