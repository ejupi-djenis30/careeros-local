# Privacy

CareerOS Local is designed to minimize disclosure of highly sensitive career data.

## Stored locally

The app may store identity and contact data, work and education history, skills, languages, achievements, goals, preferences, source documents, profile photos, resume drafts and publications, job snapshots, application tasks, working dossier drafts and dossier versions, coach conversations, and redacted AI execution metadata. Dossier drafts are stored in the local SQLite vault rather than browser storage and are removed with their application or a complete-vault erasure. Model binaries and partial downloads are stored in separate app-managed directories.

## Not collected

The project contains no product telemetry, advertising identifiers, cloud AI integration, remote prompt logging, or analytics SDK. The application does not silently upload a profile or resume. Job-provider requests are user-initiated search operations and disclose only deterministic queries built from the explicit role, strategy and preferences. Provider planning never invokes the local model, and only v3 cache records marked `deterministic-explicit` can be reused.

The daily application agenda is calculated locally from the authenticated user's scalar role and
next-action projections. It does not read task-event or dossier bodies, contact a calendar service,
or invoke the local model.

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

The source-installed `careeros` CLI and its MCP server use a separate, read-only automation
boundary. A user must first authenticate with their CareerOS password and issue a grant for one
local account. A grant has a label, an expiry and one or more of these scopes:
`system:read`, `career:read`, `resume:read`, and `applications:read`. The bearer token is displayed
only when the grant is created. CareerOS stores its SHA-256 digest, not the original token. Grants
can be listed and revoked only after another password check.

The MCP server communicates over the parent process's standard input and output. It does not open
an HTTP port, connect to a model provider or start a job search. Its tools expose bounded
projections:

- product, schema and local-model readiness;
- Career Vault completeness and fact counts without fact prose or dedicated contact fields;
- resume draft/version metadata without document bodies or artifact bytes;
- application summaries, deterministic readiness checks and a bounded next-action agenda.

The tools do not accept arbitrary paths, files, SQL or prompts. They do not expose source
documents, resume text, dedicated contact records, local storage paths, access tokens or model
prompts. User-authored labels, resume names, company names, locations and task titles can still
contain personal or sensitive text; authorizing their scope allows the connected agent to receive
those values. There are no create, update, delete, restore, export or network-search tools.

This boundary does not make an external agent private. An agent can include MCP results in a
request to its own provider. Starting the server therefore requires the explicit
`--acknowledge-agent-disclosure` flag. Issue the smallest useful scope set and short lifetime,
protect `CAREEROS_MCP_TOKEN` with the operating system's credential facilities, and revoke the
grant after use. Never store the bearer token in a repository or paste it into a prompt.

Each CLI command and MCP tool call uses the same exclusive vault lease as the desktop sidecar.
MCP releases it after bootstrap and after every call, so an idle server does not keep the desktop
closed. Before each tool read, it reacquires the lease and revalidates the token, expiry, revocation
state and original grant identity. A call made while CareerOS Local owns the vault returns
`vault_busy`; it does not become a second writer. Restore revokes all active automation grants for
the restored account, and complete vault erasure deletes the grant records.

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
