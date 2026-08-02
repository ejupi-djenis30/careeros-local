# CareerOS Local Constitution

<!--
Sync impact report
- Amendment: a fresh vault contains no installed network job provider. Reviewed native adapters
  remain dormant until the user imports a bounded provider document or pack; imports are atomic,
  non-executable and disabled unless the importing action explicitly grants network activation.
- Amendment: job providers may be added as bounded declarative user configurations, and
  external-agent grants may authorize the same typed career operations as the desktop through
  explicit read, write and execute scopes without exposing generic storage or bypassing domain
  validation.
- Amendment: destructive vault operations now persist an explicit four-state lifecycle before
  mutation, use purpose-bound recovery authority and restart-durable ownership journals, and
  clear pending state only after durable cleanup and SQLite sanitation have completed.
- Amendment: the desktop backend now exposes non-blocking liveness/readiness probes and MUST
  quiesce scheduled work, managed runtimes and writers in dependency order during shutdown.
- Amendment: browser access and refresh JWTs now share one bounded persisted session family;
  every protected access requires live family authority, while replay, logout, restore and
  complete erasure revoke or remove that authority without storing a raw bearer or access JTI.
- Amendment: browser cookie mutations use Fetch Metadata when `Origin` is absent, and every
  Node-backed npm entry point fails before work unless the exact supported Node range is active.
- Amendment: production environment, JWT, credentialed-origin and renderer API-base configuration
  now fail closed; authenticated API payloads are never dynamically compressed, and an explicit
  logout failure cannot be presented as a completed server-session termination.
- Amendment: renderer boot now carries executable raw and compressed resource budgets, loads only
  the selected bundled locale, and must not ship an application-wide icon font when an auditable
  used-icon subset can preserve the same interface.
- Amendment: content-security directives must be delivered through a channel where the target
  runtime enforces them; web response-header framing protection cannot be represented as meta CSP.
- Amendment: release shells receive repository/ref metadata only through quoted environment
  variables, reverse proxies normalize the upstream Host, and dependency automation carries an
  explicit non-security update cooldown.
- Amendment: modal navigation overlays now follow the same focus, inert-background and scroll
  isolation guarantees as modal content workflows.
- Amendment: desktop grant management may return an external-agent bearer only after
  current-account password verification, through a non-cacheable one-time response that the
  renderer never persists automatically.
- Amendment: daily-work counts and rows must share one database snapshot, and local-day
  classification must use an explicit DST-correct boundary supplied by the local renderer.
- Amendment: the daily application agenda must be derived from authenticated user-scoped
  projections, classify deadlines deterministically and disclose any bounded truncation.
- Amendment: every workflow presented as AI analysis now requires a ready, validated local model
  and fails closed instead of substituting heuristic output; owned records and deterministic
  preflight/export workflows remain available without inference.
- Version: 1.4.0 (adds zero-provider bootstrap and explicit provider-pack import).
- Ratified: 2026-07-17.
- Last amended: 2026-08-02.
- Principles: desktop ownership, local intelligence, grounded career truth, durable vault,
  bounded architecture, measurable delivery, secure distribution, accessible documents.
- Dependent artifacts: plan, specification, task and checklist templates reviewed.
-->

## Core Principles

### I. The desktop application is the product

CareerOS Local MUST install, launch, update and uninstall as a native desktop application
without requiring Docker, a shell, Python, Node.js or a manually started web server. All
application services MUST bind only to loopback, use an ephemeral authenticated session,
and terminate with the desktop process. Windows, macOS and Linux release artifacts MUST
be reproducible from source and published with checksums.
Shutdown MUST stop new scheduled work before snapshotting or cancelling background tasks, wait
within a bounded deadline for managed-runtime workers, and terminate every child process even
when the graceful path fails. Liveness MUST remain independent of database and writer activity;
readiness MUST report contention without waiting behind a long-running writer.

Rationale: a local-first product must feel owned by the user, not operated like a server.

### II. Local-only intelligence is a non-negotiable boundary

Prompts, embeddings, model outputs, profile data and documents MUST never be sent to a
remote inference service. The source tree and dependency graph MUST contain no remote-AI
client or fallback. Model acquisition is an explicit user action; inference works offline
after acquisition. Runtime endpoints MUST be loopback-only and denied by default when
their locality cannot be proven.

Rationale: privacy cannot depend on provider configuration or user vigilance.

### III. Career truth is grounded and reviewable

Every generated claim MUST reference one or more career-fact identifiers. AI MAY select,
compress and rewrite supported facts, but MUST NOT invent employers, dates, credentials,
skills, results or metrics. Structured outputs MUST pass schema, evidence and consistency
validation before persistence. Low-confidence results MUST be surfaced for review instead
of silently accepted.

Application-readiness decisions MUST be computed from versioned local records, expose every
contributing check, and produce the same report bytes for the same application state. A model
MUST NOT be required to inspect, explain or export readiness evidence.
Any workflow presented as profile analysis, opportunity analysis, matching, tailoring, coaching
or another AI-derived judgment MUST require a ready local model and MUST fail closed when local
inference or structured-output validation is unavailable. Deterministic checks MAY remain
available under their own accurate labels, but MUST NOT be substituted for, persisted as or
displayed as completed AI analysis.
Claims that a published document is available MUST be backed by readable bytes inside the approved
data root that match the immutable digest and declared length; database metadata alone is not
evidence of artifact availability.
Deterministic provider queries MUST use only user-entered search instructions and explicit
preferences. CV prose, LLM-normalized profile fields and unconfirmed model intent MUST NOT become
provider queries without a separate user confirmation.
User-defined job providers MUST be declarative rather than executable. Their network requests MUST
use explicit opt-in, credential-free HTTPS destinations outside loopback and private networks,
bounded same-origin paths, disabled redirects and ambient proxies, bounded pagination and response
bytes, and validated JSON or HTML extraction rules. Provider credentials and secret-looking header
values MUST never enter logs, exports, tool results or list responses; configuration errors MUST
fail closed before a request is made.
A new vault MUST register no network job provider. A reviewed native adapter MAY ship as dormant
application code, but it MUST NOT appear in the active registry until the user explicitly imports a
strict provider document or provider pack that references its allowlisted adapter identifier.
Provider documents and packs MUST be bounded JSON data, MUST NOT contain executable modules or
stored credentials, MUST validate completely before an atomic import, and MUST remain disabled
unless the import or a later revision-checked action explicitly enables network access. Bundled
pack discovery is not installation or consent.

Rationale: accuracy is more valuable than fluency in high-stakes career material.

### IV. Small-model quality is measured, not assumed

AI workflows MUST be designed for locally runnable small models through bounded context,
task-specific schemas, deterministic retrieval, constrained decoding and selective repair.
Every AI behavior change MUST be evaluated against a versioned offline golden set. Release
gates MUST cover schema validity, evidence coverage, hallucination rate and task accuracy;
latency and memory are recorded by model profile.

Rationale: compact models become dependable through system design and evidence.

### V. The career vault belongs to the user

SQLite and user-selected local files are canonical. Schema migrations MUST be transactional,
backed up when destructive, and tested from both an empty database and the supported prior
version. Users MUST be able to export, import and delete their complete vault in documented,
non-proprietary formats. Application updates MUST preserve data and generated documents.
Portable backups MUST be inspectable without changing the active vault. A successful inspection
MUST validate bounded archive structure, member digests, record relationships and persisted-file
bindings while returning only content-free metadata. Saving a backup MUST NOT be described as
verified until the bytes at the selected destination match the server-issued digest. Plain ZIP
archives MUST be identified accurately as neither encrypted nor authenticated.
Manual opportunity captures MUST use a server-owned per-user namespace and idempotent retries;
client identifiers MUST NOT merge private captures across users. Concurrent application writers
MUST advance revisions with an atomic compare-and-swap, and derived board projections MUST never
replace the immutable event history.
Daily-work views MUST read only authenticated user-scoped application projections, MUST classify
deadlines deterministically from an explicit time window, and MUST disclose when a bounded result
set omits lower-priority items. They MUST NOT replay or expose another user's event payloads.
Counts and rows in one daily-work response MUST come from one database statement or an explicitly
verified snapshot transaction. Local-day boundaries MUST be supplied as timezone-aware instants
calculated by the renderer's local calendar, not reconstructed from a fixed UTC offset.
Reset, restore and complete erasure MUST persist one of `reset_pending`, `restore_pending` or
`erasure_pending` before the first destructive mutation; `ready` is the only state that permits
normal workspace authority. Restore file ownership MUST be recorded before publication in a
checksummed, restart-durable, per-account journal with owner-scoped staging. Retries MUST require
the same verified archive fingerprint, while complete erasure MUST remain available when the
archive is lost. Restore MUST accept only canonical identifiers and managed storage paths,
preserve files that have become referenced by another account, revoke sessions and grants, and
restore schedules disabled. A failed restore may clear pending state only after journal-owned
exclusive files are durably removed and SQLite rollback remnants are sanitized; otherwise it
MUST retain recoverable pending state. Startup cleanup MUST be confined to recognized temporary
files inside managed asset and resume namespaces.

Rationale: local storage without portability and recovery is only local lock-in.

### VI. Boundaries stay explicit

Desktop lifecycle, transport, use cases, domain rules, persistence, model runtimes, source
connectors and document rendering MUST remain separate. Domain code depends on ports rather
than framework implementations. Route handlers contain no business orchestration. Python
modules SHOULD remain below 300 lines and React components below 150 lines; exceptions MUST
be justified in the feature plan with a decomposition follow-up.

Rationale: the heavy refactor must reduce accidental coupling rather than relocate it.

### VII. Production evidence precedes release

Acceptance criteria MUST be executable. Unit tests cover domain rules; contract tests cover
process and API boundaries; integration tests cover SQLite, migrations, inference and export;
end-to-end tests cover installation, first launch, restart and upgrade. Tests deny network by
default. A release is incomplete if lint, type checks, tests, AI evaluations, packaging, SBOM,
license policy, vulnerability scan or artifact smoke tests fail.
Renderer boot resources MUST have executable raw and compressed budgets. Language catalogues and
other view-independent assets MUST remain bundled for offline use but load only when selected or
needed; a build warning MUST be resolved through measured byte reduction rather than cosmetic
chunk relocation.
Dependency update automation MUST define an explicit review cooldown for routine updates across
every managed ecosystem without delaying security updates.

Rationale: production-grade is a verified state, not a label.

### VIII. Safety and accessibility are product behavior

Logs MUST exclude profile bodies, prompts, tokens, document text and contact details. The
desktop shell MUST enforce a restrictive content security policy, disable arbitrary navigation,
validate IPC messages and avoid renderer privileges. Core workflows MUST be keyboard accessible.
Each content-security directive MUST use a delivery mechanism the target runtime enforces.
Browser framing protection MUST remain in web response headers instead of an ineffective meta
directive, while the desktop runtime retains its native CSP configuration.
Production mode, the reviewed JWT algorithm, credentialed browser origins and renderer API bases
MUST use canonical allowlisted values and MUST fail closed on wildcard, ambiguous or malformed
configuration. Authenticated API responses MUST NOT use dynamic compression. An explicit sign-out
failure MUST immediately hide the private workspace, report that the server session was not ended
and offer a retry instead of exposing login controls or claiming success.
Each browser access and refresh token MUST carry the same persisted session-family identifier.
Every protected access MUST bind its signed subject and family identifier to a live, unexpired,
non-revoked family row; a JWT alone is insufficient authority. Refresh tokens MUST be single-use,
and their current JTI MUST be stored only as a one-way digest. Rotation MUST compare-and-swap that
digest; reuse of an older token MUST revoke the family. Logout MUST atomically revoke every valid
family presented by its cookie and bearer, including an already rotated refresh token. A failed
logout commit MUST roll back, clear automatic refresh cookies, report failure and retain only an
in-memory bearer for explicit retry. Session rows MUST be bounded per account, excluded from
portable archives, revoked on restore and removed by complete erasure. Raw access and refresh
tokens and access JTIs MUST NOT be persisted. Once revocation or deletion commits, new protected
requests using that family MUST fail; a request authorized before that commit is not retroactively
cancelled.
Normal session access and refresh MUST fail while vault maintenance is pending. Recovery access
MUST be password-reissued, purpose-bound, non-refreshable and accepted only by the matching
maintenance operation; it MUST NOT authorize ordinary workspace routes or agent grants. Logout
MUST invalidate even the special erasure-recovery family so the presented bearer cannot be
reused, while a subsequent correct-password login MAY issue a fresh maintenance authority.
Reset and erasure MUST revoke any session family created after the initial maintenance snapshot
before declaring completion.
Repository, ref and commit metadata MUST enter release shell commands through quoted environment
variables instead of expression interpolation. A web reverse proxy MUST send the backend a fixed
allowlisted Host rather than reflecting the client-supplied Host header.
Creating an external-agent grant from the authenticated desktop MUST require current-account
password verification. Repeated failures MUST be isolated to that account and MAY pause new
issuance, but a correct current password MUST remain able to revoke an existing grant. The bearer
MAY appear only in the explicit non-cacheable issuance response, MUST be shown as a one-time
secret, and MUST NOT be written to logs, browser storage, application storage or the clipboard
without a direct user action. Grant lists expose only owned non-secret metadata and MUST keep
every active grant visible and revocable.
External-agent authority MUST be purpose-bound through explicit read, write and execute scopes.
Any career workflow available to an authenticated desktop user SHOULD have a typed agent operation
with the same ownership checks, bounded schemas, local-model readiness gates, revision compare-and-
swap and durable domain-service invariants. Grants MUST NOT expose generic SQL, arbitrary files,
provider code execution, stored credentials, raw session authority, restore, erasure or a way to
bypass normal validation. Every tool call MUST reacquire the vault lease and revalidate the grant;
revocation, expiry and vault lifecycle state MUST fail closed before mutation.
Modal workflows and modal navigation overlays MUST identify themselves to assistive technology,
contain keyboard focus while open, make obscured content inert, lock background scrolling, close
with Escape where safe, and return focus to their opener when it remains available.
ATS resumes MUST be text-extractable and photo-free; visual templates MUST remain readable
without color and strip image metadata. PDF and DOCX exports are generated locally and checked
for required sections, non-empty text and overflow.

Rationale: private data and career documents deserve secure, inclusive defaults.

## Product gates

- No code, package, environment variable or UI path may enable remote AI inference.
- No hidden network request may occur during launch, editing, inference, rendering or tests.
- Job-source access and model download are separate, explicit, auditable capabilities.
- The vault, manual editing, portability, deterministic readiness and existing exports remain
  usable without inference; an AI analysis action is blocked until the local model passes the
  product readiness check.
- A failed model call never degrades into an unlabeled heuristic match or completed AI result.
- A generated career claim without evidence is rejected before it reaches the user.
- External-agent access remains explicitly scoped and typed; read, write and execute grants may
  operate normal career workflows but never turn the desktop session token into an MCP credential,
  expose generic storage or store the one-time bearer for convenience.
- The default installer starts on a clean supported OS without developer tooling.
- The desktop app must recover cleanly from a crashed local model or backend process.
- A killed reset, restore or erasure resumes safely from durable lifecycle state; an unrelated
  normal session cannot bypass it, and lost-archive restore recovery can always converge by
  complete erasure.
- Release artifacts must be signed where credentials are available; unsigned development
  artifacts must be labeled clearly and must still include checksums and an SBOM.

## Spec-driven workflow

Every substantial change follows this order:

1. specify user outcomes, constraints and independently testable acceptance scenarios;
2. clarify only decisions that materially alter scope or safety;
3. research unknowns using primary sources and record decisions with alternatives;
4. plan architecture, migrations, contracts, packaging and constitution compliance;
5. create dependency-ordered tasks with tests and release evidence;
6. implement in thin, independently verifiable slices;
7. analyze artifact consistency, converge remaining work and rerun every release gate.

## Governance

This constitution supersedes every project-local agent instruction and historical document.
Amendments require a written impact report and semantic version change. Removing or weakening a
privacy, evidence, durability or release gate is a major change; adding a mandatory principle is
minor; clarification without changed obligations is patch. Every plan MUST perform a constitution
check before research and again before release. Exceptions require owner approval, an expiry date
and a tracked remediation task; there are no implicit exceptions.

**Version**: 1.3.0 | **Ratified**: 2026-07-17 | **Last amended**: 2026-08-02
