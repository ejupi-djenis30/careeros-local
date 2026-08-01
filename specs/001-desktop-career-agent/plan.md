# Implementation Plan: CareerOS Local Desktop Career Agent

**Branch**: `codex/001-desktop-career-agent` | **Date**: 2026-07-17 | **Spec**: [spec.md](spec.md)

**Input**: Owner-approved full product migration, local-first AI hardening, desktop
distribution, profile/goal depth, automatic resumes and editable resume canvas.

## Summary

CareerOS Local becomes a Tauri v2 desktop product around the existing React workspace and
a frozen Python sidecar. Tauri owns one authenticated loopback process on a random port;
the sidecar owns the SQLite vault and a managed `llama.cpp` process required by analysis workflows.
Runtime and
model acquisition are explicit, pinned and integrity-verified. The existing deterministic
career-profile, goal, resume and canvas capabilities remain the source of truth while a new
bounded AI package adds schema-constrained generation, deterministic evidence retrieval,
semantic validation, limited repair and offline evaluation for compact local models.

The migration also removes legacy naming and scratch-output conventions, decomposes the
largest AI/search orchestrators behind stable facades, adds non-sensitive AI audit records,
and introduces per-platform installer CI with checksums, SBOMs and smoke tests. The v1.1
release path canonicalizes every native filename before hashing, assembles one exact manifest,
attests all public assets and binds publication to a verified annotated tag through an
idempotent GitHub Release state machine. Application Readiness adds a bounded deterministic
domain service that joins only owned local records, emits inspectable checks and exposes
canonical JSON/Markdown exports without introducing persistence or migration work.
The source-installed automation interface adds a second entry point for fixed local reads: a
human JSON CLI and an MCP stdio server share one scoped facade. Revocable user-bound grants,
exclusive vault leasing, typed result limits and explicit agent-disclosure acknowledgement keep
that interface narrower than the desktop API.
Browser refresh authentication uses a separate bounded stateful family. The JWT carries a
non-secret session id and one-time JTI; SQLite stores only the current JTI digest in one of eight
database-unique account slots. Compare-and-swap rotation detects reuse and revokes the family,
while logout, restore and erasure close the corresponding authority without exporting it.

## Technical Context

**Language/Version**: Python 3.12.13; Rust 1.84+ (current workspace 1.96); JavaScript/JSX
on Node 24.18.0 LTS

**Primary Dependencies**: Tauri 2.11, React 19, Vite 7, FastAPI 0.139, SQLAlchemy 2,
Alembic 1.18, Pydantic 2.13, MCP Python SDK 1.28.1, PyInstaller 6.21,
llama.cpp server b9637

**Presentation**: dependency-free React message catalogue with English as the clean-install
default and Italian as an on-device, user-selected alternative; no locale service or egress

**Storage**: SQLite career vault in the operating-system application-data directory, including
bounded digest-only browser session families excluded from portable content; content-addressed
local assets; atomic JSON manifests for managed runtime/model state

**Testing**: pytest, Vitest/Testing Library, Cargo tests, mocked process/download contract
tests, migration round-trips, packaged-sidecar smoke tests, Tauri installer build matrix,
offline AI golden-set evaluator

**Target Platform**: Windows x64/arm64, macOS x64/arm64 and Linux x64/arm64 desktop; browser and Docker
remain contributor-only development modes

**Project Type**: Cross-platform desktop application with a local Python service sidecar,
a source-installed read-only CLI/MCP entry point, and a managed native model-runtime child
process required for AI analysis

**Performance Goals**: warm local API reads p95 below 200 ms for a 10,000-record vault;
desktop shell interactive within 5 seconds after sidecar readiness; compact-model structured
task median below 45 seconds on reference CPU; canvas interactions at 60 fps for 100 blocks;
application readiness calculation below 100 ms for one application with 300 selected facts

**Constraints**: no remote inference or API keys; zero hidden startup egress; installer does
not bundle the 1.83 GB model; all service/model endpoints loopback-only; MCP uses stdio only;
one active vault writer; no user-content logging; automation tools are read-only, scoped and
bounded; release builds are native per operating system

**Scale/Scope**: one user and one vault per installation; up to 250,000 imported records,
20,000 archive members, 100 resume blocks, 50 resume versions per draft, and five AI task
families in the first evaluation suite

## Constitution Check

### Pre-research gate

- **PASS — Native product**: Tauri produces platform installers and owns sidecar lifecycle;
  no production path requires Docker, Python, Node.js or a shell.
- **PASS — Local-only AI**: only explicit loopback adapters exist; managed downloads are
  model/runtime acquisition rather than inference, and there is no cloud fallback.
- **PASS — Grounding**: schemas include evidence identifiers and trusted persistence follows
  citation and semantic validation.
- **PASS — Vault ownership**: SQLite stays canonical; migration, backup, restore and deletion
  are retained and tested across upgrades.
- **PASS — Security boundary**: a random loopback port and per-launch session token protect
  the sidecar; Tauri exposes one read-only bootstrap command and a restrictive CSP.
- **PASS — Refresh replay boundary**: browser refresh JWTs are single-use against a bounded
  digest-only session family; CAS loss or old-token reuse revokes that family, and raw JWTs never
  enter SQLite or portable archives.
- **PASS — Release evidence**: the plan includes unit, contract, integration, evaluation,
  supply-chain, packaged-artifact and lifecycle gates.
- **PASS — Deterministic readiness**: the application preflight reads only local owned records,
  publishes every weighted check, omits storage paths and produces canonical exports without AI.
- **PASS — Truthful analysis**: non-AI Vault, portability, document and deterministic readiness
  workflows remain available without a model, while analysis fails closed unless the loopback
  runtime is ready and a content-free schema probe validates structured output.
- **PASS — Private daily agenda**: the new daily-work read model uses only owned scalar
  projections, bounded time-window inputs and explicit omission counts; it neither replays event
  payloads nor invokes local or remote inference.
- **PASS — Agent least privilege**: the CLI and MCP server authenticate an expiring user-bound
  grant, acquire the desktop lease for each read, expose only fixed bounded results, open no
  listener and require acknowledgement before results can pass to an external agent client.

### Post-design gate

- **PASS**: sidecar and model-manager state transitions are explicit in `data-model.md`.
- **PASS**: REST, desktop IPC and structured AI interfaces are versioned in `contracts/`.
- **PASS**: model/runtime URLs and hashes are catalog data, never arbitrary user input.
- **PASS**: portable vault formats do not depend on the desktop shell.
- **PASS WITH TRACKED DECOMPOSITION**: legacy files above the constitution guideline are
  wrapped by new bounded packages and split as part of this feature; see Complexity Tracking.

### v1.1 release-hardening gate

- **PASS — Deterministic identity**: platform jobs copy smoke-tested bundles to canonical,
  whitespace-free names before checksum or attestation generation.
- **PASS — Exact evidence**: per-target manifests converge into one global release manifest;
  the supply-chain archive has a closed regular-file inventory and published SBOMs are bound to
  the native package subjects.
- **PASS — Trusted provenance**: only a GitHub-verified annotated tag resolving to the checked-out
  commit and contained in the current default branch can reach the publication state machine.
- **PASS — Durable publication**: the publisher uses authenticated pagination, an exact body
  contract and remote name/size/digest verification to recover without clobbering trusted data.
- **PASS — Read-only rehearsal**: pull-request, scheduled and manual builds retain read-only
  repository permissions; only a tag-push-only job receives OIDC, attestation and publication
  permissions.

## Project Structure

### Documentation (this feature)

```text
specs/001-desktop-career-agent/
├── agent-interface-analysis.md
├── agent-interface-convergence.md
├── checklists/requirements.md
├── contracts/
│   ├── ai-contracts.schema.json
│   ├── desktop-ipc.schema.json
│   └── openapi.yaml
├── data-model.md
├── plan.md
├── quickstart.md
├── research.md
├── spec.md
└── tasks.md
```

### Source Code

```text
backend/
├── automation/
│   ├── cli.py
│   ├── facade.py
│   ├── grants.py
│   ├── mcp_server.py
│   ├── models.py
│   ├── runtime.py
│   └── schemas.py
├── ai/
│   ├── contracts.py
│   ├── evaluation.py
│   ├── grounding.py
│   ├── orchestrator.py
│   ├── retrieval.py
│   └── task_specs.py
├── desktop/
│   ├── lifecycle.py
│   ├── session.py
│   └── settings.py
├── inference/
│   ├── catalog.py
│   ├── llama_cpp.py
│   ├── managed_runtime.py
│   ├── model_catalog.json
│   ├── ollama.py
│   └── ports.py
├── search/
│   ├── matching/
│   ├── normalization/
│   ├── planning/
│   └── service.py
└── main.py

desktop/
├── backend_main.py
└── careeros-backend.spec

frontend/
├── src/
│   ├── i18n/
│   ├── features/local-model/
│   ├── lib/client.js
│   └── platform/desktop.js
└── src-tauri/
    ├── capabilities/main.json
    ├── icons/
    ├── src/{commands,lifecycle,main}.rs
    ├── Cargo.toml
    └── tauri.conf.json

scripts/
├── build_backend_sidecar.py
├── package_desktop.ps1
└── package_desktop.sh

tests/
├── ai/fixtures/
├── backend/ai/
├── backend/automation/
├── backend/desktop/
├── desktop/
└── frontend/
```

**Structure Decision**: Preserve the tested domain and REST layers in Python, expose them
only through an authenticated loopback sidecar, and keep native lifecycle/security in the
small Rust shell. Place accuracy policy in `backend/ai` and runtime mechanics in
`backend/inference`; neither domain services nor UI components depend on a concrete runtime.
The former `backend/services/llm_service.py` and `search_service.py` remain temporary import
facades until consumers are migrated, then shrink below the constitutional guideline.

The presentation layer keeps language state separate from domain data. Navigation, the
workspace shell and demo-facing components resolve copy through `frontend/src/i18n/`; the
selected language is a local interface preference and never changes stored career facts.

The agent interface is not another transport over the desktop API. `backend/automation` configures
the existing vault before database imports, acquires the same process lease for each access,
authenticates a stored grant digest and maps domain services into fixed DTOs. The CLI serializes
those DTOs as JSON. The MCP entry point registers only the allowed tools and writes protocol
messages over stdio. Neither entry point accepts a desktop session token, arbitrary query or raw
file path.

## Delivery Phases

### Phase A — Identity, hygiene and contracts

Rename every product/package identifier, replace all documentation, remove obsolete output
conventions, establish the feature artifacts, and add tests that reject the old repository
name and remote-AI vocabulary in runtime code.

### Phase B — Desktop runtime

Add the frozen backend entry point, desktop environment validation, session-token middleware,
Tauri shell, readiness splash, graceful shutdown, single-instance behavior, app-data paths,
icons and platform packaging scripts. Browser development stays available without weakening
desktop checks. Treat exit as a coordinated protocol rather than an immediate child kill: Tauri
prevents the first exit request, posts to a hidden desktop-only loopback route with the per-launch
session token, waits for the sidecar supervisor to observe termination, and forces a direct kill
only after a fixed deadline. Uvicorn drains through FastAPI lifespan cleanup; a parent-death
watchdog requests the same path before its own hard timeout on platforms where process containment
has not already acted. On Windows, assign the sidecar to a kill-on-close Job Object so abrupt
native-parent death immediately contains its managed local-runtime descendants. Unit tests cover
token transport, idempotent exit state and watchdog ordering; packaged lifecycle acceptance remains
the cross-platform zero-orphan release gate.

### Phase C — Managed local model

Add a signed catalog with pinned llama.cpp runtime assets and the official Qwen3 1.7B GGUF.
Implement cancellable atomic acquisition, safe archive extraction, SHA-256 verification,
disk-space checks, process health/restart limits and cleanup. Keep Ollama as an explicitly
local contributor adapter, not the production runtime.

### Phase D — Small-model accuracy system

Introduce task contracts, schema-constrained decoding for both llama.cpp and Ollama,
temperature-zero task profiles, deterministic BM25 evidence selection, exact evidence-ID
validation, domain validation and a single bounded repair. Migrate coach, profile extraction,
search planning, job normalization and matching incrementally behind the stable facade.

### Phase E — Audit, evaluation and decomposition

Persist content-free execution metadata, add a versioned synthetic golden set and metrics,
then split legacy orchestration by task. Every accepted AI output records contract version,
evidence count and validation result without prompts or outputs.

### Phase F — Distribution evidence

Build native artifacts on each target OS, smoke-test the frozen sidecar and installer, create
checksums/SBOMs, audit Python/npm/Rust dependencies, scan source and artifacts, and publish a
draft GitHub Release only from an explicit version tag.

### Phase G — Immutable v1.1 release contract

Stage every platform bundle under a deterministic public name and emit a checksummed, validated
target manifest.
On a separate pinned runner, reject missing, duplicate, unsafe or unexpected files; validate the
closed supply-chain evidence set; create a deterministic evidence archive, canonical SBOM assets,
the canonical public `LICENSE`, `release-manifest.json` and `SHA256SUMS`; then independently
re-verify the assembled candidate. Embed the same license bytes as a Tauri resource and require
every platform smoke gate to find them in the mounted, extracted or installed native payload.
For a trusted tag push, attest every checksum-listed asset plus the checksum file, add CycloneDX
SBOM attestations for the native subjects, and verify repository, workflow, source ref, source
digest, predicate and hosted-runner identity before publication. The publisher discovers drafts
through bounded authenticated pagination, accepts only its exact durable contract, resumes exact
partial uploads, reconciles ambiguous API transitions and treats an already exact immutable
latest release as a no-write success.

### Phase H — Deterministic Application Readiness Pack

Add a focused `backend/applications/readiness.py` service below the transport layer. It loads the
owned application, candidate profile and linked immutable resume version, evaluates a fixed set of
weighted checks, and hashes canonical report content. Routes return the structured report or stream
canonical JSON/Markdown bytes with matching digest headers. The React application detail loads the
report on demand, shows score, state and corrective actions, and downloads either representation
through the existing authenticated loopback client. A revision-checked preparation PATCH updates only
the captured role identity, description, application route and owned resume link through a conditional SQLite write;
it appends a content-free field-name audit event so every blocker has an in-product resolution path.
Artifact availability calls the existing `backend.storage.atomic.read_verified` boundary for every
owned artifact row, which enforces data-root containment, readability and SHA-256 integrity; the
check also compares the immutable declared byte length. Both verified PDF and DOCX with no failed
row pass. One verified format with no integrity failure warns that the pack is incomplete. Any
unsafe, unreadable, missing, digest-mismatched or size-mismatched recorded artifact blocks sending,
as does having no verified format. Evidence reports only recorded/verified/unavailable format names,
never storage paths or digests.

Application Detail is rendered through a body portal as a labelled modal dialog. While open it
makes the workspace background inert and hidden from assistive technology, locks body scrolling,
queries focusable descendants on every Tab press so preparation-editor controls join the trap,
closes on Escape and restores the captured opening control. The drawer keeps full-width mobile
layout, uses the dynamic viewport height and contains overscroll. No schema change, model process,
remote request or background calculation is required. Backend tests cover ownership, stale writers,
real stored artifacts, deletion/corruption/path containment/read failures, freshness, deterministic
exports and redaction; frontend tests cover dialog semantics, dynamic focus, corrective navigation,
editing and downloads.

### Phase I — Private daily-driver workflow

Treat provider listings and manual captures as different trust domains. `JobService` derives a
stable opaque manual identifier from the authenticated user namespace and listing identity,
discards supplied manual ids and resolves same-user retries before creating a relationship. This
ships with the unreleased importer, so no historical-row migration is required. Pydantic rejects
unknown and oversized import fields at transport entry.

The provider planner consumes only `role_description`, `search_strategy` and explicit preferences
and never calls an LLM. Cache v3 records carry `deterministic-explicit` provenance and an
explicit-input-only fingerprint; legacy and model-derived entries are replaced. LLM-normalized
profile fields remain available to downstream local matching but cannot cross the provider
boundary. Integer zero is preserved as a disable signal; only `NULL` uses a configured default.

Application stage, task and dossier writers share `_advance_revision`, which performs a conditional
revision update and maintains stage or next-action projection columns in the same transaction as
the append-only event. Task detail replay groups by task id and revision, rejects incoherent or
regressive history and selects the maximum contiguous revision independent of occurrence time. The
board constructs its narrow response from scalar role, latest-event and next-action projections in
one SQL query that cannot select the event payload or `job_snapshot`.

The dossier UI uses bounded repeatable rows for requirements/evidence, answers and checklist items.
It never drops a partial question-answer pair silently, keeps draft state on validation errors and
provides named add/remove controls in English and Italian. A resume change removes only stale
evidence IDs with an accessible notice. The API accepts only UUID evidence ids owned by the linked
immutable resume, stores each fact snapshot once in a v2 catalog, and preflights input, event,
artifact and ZIP byte limits. Backend cross-user/concurrency/replay/schema tests and
frontend multi-row/accessibility tests provide the release evidence.

### Phase J — Mandatory local analysis capability

Keep the verified managed llama.cpp catalog and authenticated random-loopback runtime as the
desktop default. When Windows application-control policy blocks that runtime, allow an official
Ollama installation as a production local fallback on an allowlisted loopback endpoint; it must
pass the same identity, schema, grounding, and readiness checks, with cloud endpoints disabled. Extend the
model status contract with an explicit required-analysis boundary and add an authenticated
readiness probe that checks endpoint policy, runtime reachability, configured-model availability
and one temperature-zero schema-constrained response containing no career data. The probe validates
the response with a strict Pydantic contract and reports stable diagnostic codes only.

After authentication, expose model setup as a keyboard-accessible prerequisite panel. Users may
still open and edit the Vault, inspect existing documents, use portability and calculate/export the
deterministic application preflight while the model is absent; every navigation path that claims AI
analysis remains visibly locked until the probe passes. Opportunity-search startup performs a cheap
server-side ready-state precondition, and search matching removes every deterministic fallback:
runtime, circuit, timeout or structured-output failure returns an explicit failed analysis state and
persists no substitute score. Heuristic scoring remains an accurately labelled pre-filter only.

No database migration is required. Backend tests cover loopback/schema diagnostics, search
preconditions and fail-closed matching. Frontend tests cover setup, retry, unlock, English/Italian
copy, keyboard operation and no analysis-content rendering before readiness.

### Phase K — Private daily application agenda

Add a focused `ApplicationAgendaService` read path over the same scalar fields used by the board
instead of growing the existing application facade. One CTE/window statement excludes rejected,
withdrawn and archived applications, calculates one UTC `generated_at`, consumes a validated
timezone-aware next-local-midnight instant calculated by the browser's local calendar, and
classifies projected next actions as overdue, due today, upcoming, undated or beyond the bounded
horizon. Active applications without a projection become explicit `needs_action` rows. Aggregate
counts and limit-ranked item rows are joined inside that statement so concurrent writes cannot
produce mixed snapshots.

The response reports active, visible, later and truncated counts before applying the caller's
bounded row limit. Ordering is stable: classification urgency, due instant, task priority, least
recent activity and application id. It selects no `job_snapshot`, event or dossier payload and
requires no migration or model process.

The Applications page loads this agenda independently of the board, so an agenda error cannot
remove manual pipeline access. Agenda rows are native buttons that open the existing accessible
detail dialog and retain the existing opener-focus behavior. A managed timer refreshes at the
earliest returned future deadline or next local midnight; focus and visible-state restoration also
refresh, while every superseded request and timer is cancelled. English and Italian labels explain
that the queue is local and deterministic. Visible heading and description text drive ARIA
relationships. Chromium validates real 320 px geometry and WCAG AA contrast. Backend tests cover
DST boundaries, ordering, snapshot coherence, omission counts, invalid bounds, query plan and
cross-user isolation; frontend tests cover rendering, refresh lifecycle, failure independence and
row navigation.

### Phase L — Backup assurance center

Extract one non-mutating archive preflight from the existing restore boundary. The preflight reuses
the bounded ZIP/member validation, typed row decoding, relationship checks, application-event replay
and file-binding verification, but separates archive validity from destination conflicts. It returns
only a fixed inspection schema: archive version and digest, creation time, per-table and total record
counts, archive/file byte totals, compatibility, current restore eligibility and stable verification
or warning codes. It never returns archive member names, storage paths, user identifiers, prompts,
model output, document text or profile fields.

Expose preflight through one authenticated, rate-limited multipart endpoint. A populated vault may
inspect any supported backup; it only makes `restorable` false and adds a stable empty-vault warning.
Restore remains the existing explicit endpoint and retains the vault lock, transactional rollback,
path containment and local-analysis quarantine. No schema migration or model process is required.

The Home recovery panel adds a separate backup-verification picker and an accessible English/Italian
summary. The desktop save path consumes the export response digest, writes a unique `.part` sibling,
re-reads and hashes it, preserves an existing destination through a unique rollback sibling, renames
the verified file, re-verifies the final path and cleans temporary files on every exit. Browser
downloads are labelled as prepared downloads because a web renderer cannot inspect the eventual
filesystem destination. Tests cover historical/current success, adversarial archives, zero mutation,
populated-vault inspection, final-byte verification, rollback faults, service behavior and keyboard
accessibility.

### Phase M — Scoped CLI and MCP reads

Add one migration for expiring, revocable automation grants. Authorization requires the CareerOS
username and an interactive password, binds the grant to that user and returns the random bearer
token once while persisting only its SHA-256 digest. Four fixed scopes cover system/model status,
Career Vault counts, resume metadata and application projections.

Bootstrap the source-installed command before normal database imports. It resolves the native
application-data directory, verifies the installation secret and Alembic head, and holds
`desktop_instance_lease` for each command. MCP uses it during bootstrap and reacquires it for every
tool call while releasing it between calls. Each tool read also revalidates the grant. Only
authorization may apply a pending migration; normal reads fail closed. This prevents an agent and
the desktop sidecar from accessing the vault concurrently without keeping the desktop closed while
MCP is idle.

Map existing domain services through a focused read-only facade. DTOs exclude raw resume and
source-document bodies, contact fields, prompts, artifact bytes, tokens and storage paths, while
list sizes and agenda horizons remain bounded. Publish the same reads as JSON CLI commands and as
scope-filtered MCP stdio tools. Require `--acknowledge-agent-disclosure` before serving MCP because
the external client, not CareerOS, decides whether results are sent to a remote provider.

Cover digest-only token storage, expiry, revocation, wrong-user access, scope enforcement,
zero-mutation reads, output bounds, official in-memory MCP negotiation and a real stdio subprocess.
Portability tests prove restore revokes active grants; deletion tests prove complete erasure
removes them.

Add an Agent Access center to the authenticated desktop without widening the MCP transport. A
focused FastAPI router reuses the grant service and current user id, re-verifies the account
password for create and revoke, bounds failed checks per account, returns every response as
non-cacheable, and exposes only `GrantView` metadata from list/revoke. Repeated failures may lock
new issuance. During that window, the route does not inspect more revoke passwords or clear the
lock; the authenticated desktop session may only revoke an owned grant.
The service caps new active grants and lists every active row plus bounded recent history ordered
by the transition that removed authority. A successful grant mutation trims only that owner's
inactive tail to 100 rows in bounded batches; active and neighboring-account rows are excluded.
Immediate retries remain idempotent while a revoked row is inside that disclosed retention window.
The create response is the one exception: it returns the new bearer once and never persists or
logs it. The desktop access token remains an API credential only and is never accepted by the CLI
or MCP server.

Load the Agent Access page lazily from the existing workspace shell. Keep the one-time bearer in
component state only, clear it on dismissal and unmount, and copy it only from an explicit button.
Wait on ordinary navigation and sign-out while issuance is unresolved; if a forced unmount still
receives a successful result, immediately attempt a compensating revocation. A forced sign-out
must wait for that cleanup before invalidating the authenticated server session.
The page explains each fixed read scope, the exclusive vault lease, the external client/provider
boundary and the current source-install requirement. It lists owned grants with active, expired
and revoked states, supports password-confirmed revocation, and prints token-free Codex and Claude
Code configuration templates. Backend tests cover password verification, ownership, no-store
headers, token non-reappearance and rate-safe errors; frontend tests cover service calls, cleanup,
copy intent, failure preservation, navigation and keyboard semantics. Copy and owner guidance state
that a hard process termination can prevent best-effort cleanup and require the user to reopen the
register and revoke an unfamiliar or unsaved grant. A production-build Chromium gate covers
WCAG 2.2 AA, EN/IT, keyboard entry, responsive overflow and post-exit bearer absence.

Credentialed browser origins use an exact allowlist rather than a catch-all localhost-port regex.
The Compose profile publishes only Nginx; the backend remains on the private network. Container
and native Uvicorn runtimes ignore forwarded client-identity headers, so SlowAPI keys cannot be
selected by a direct `X-Forwarded-For` value.

### Phase N — Durable application dossier drafts

Add one `application_dossier_drafts` row per Application, separate from immutable timeline events.
The row binds an owned linked Resume Version and the Application revision at which it was saved,
while its own monotonic revision supplies compare-and-swap create, update and delete semantics.
Draft Pydantic contracts retain incomplete rows for autosave but forbid unknown fields, blank or
duplicate stable client ids, oversized strings, excessive row/evidence counts and oversized
aggregate JSON.

Expose authenticated GET, rate-limited PUT and rate-limited DELETE routes. Reads are private and
non-cacheable; every write first resolves the owned Application and Resume Version. The dossier
workspace loads before editing, debounces writes into SQLite, never uses browser storage and keeps
all visible fields through transport, validation and conflict failures. An explicit conflict action
rebases the visible copy onto the latest saved draft revision. Publication from the workspace waits
for the current save, compares the publishable projection to that exact revision and deletes the
draft only in the same commit that advances the Application and records its immutable event. The
existing no-draft API publication path remains available for compatibility.

Advance portable archives to format v6 by adding the draft table after its Application and Resume
dependencies. Preflight validates required identifiers and timestamps, one row per Application,
monotonic revisions, bounded content and every database relationship before any destination write.
Historical v1-v5 archives decode an empty draft table. Migration tests inspect constraints and
exercise downgrade/upgrade; round-trip, malformed-archive, cross-user, CAS, publication-failure,
autosave and accessibility tests cover the full boundary.

### Phase O — CV-first first result

Keep source storage and candidate extraction on the existing authenticated Career Vault boundary.
Do not make the source endpoint create profiles implicitly: the profile's revision contract and the
document endpoint remain separate, observable operations. The profile workspace instead recognizes
that its initial GET returned `404`. When the user explicitly imports a source, it first writes the
current minimum profile through `PUT /career-profile`; only a successful response may release the
selected file to `POST /career-profile/sources`. This preserves the existing path-containment,
archive-size, extraction and provenance controls without inventing a second bootstrap contract.

Make the CV-first route visible from the verified Home setup checklist alongside manual entry.
For a missing profile, keep the source importer before the long-form editors for the lifetime of
that page so the component and selected file are not remounted after the bootstrap write. Explain
that extraction is deterministic and local, retain the file after profile or upload failure for an
explicit retry, and keep accepted candidates in the existing `imported` state. After acceptance,
provide a keyboard-operable action that focuses the facts review heading; confirmation and the final
Vault save remain explicit user actions.

No schema, model, runtime, provider, telemetry or new network boundary is required. Frontend tests
cover call ordering, failure containment, retry state, existing-profile behavior, imported status,
focus and bilingual copy. The constitution remains unchanged: this slice strengthens Principles I,
III, V and VIII and does not alter any local-AI or source-consent gate.

### Phase P — Mobile workspace navigation isolation

Keep the existing CSS breakpoint and drawer DOM order, but treat an opened mobile sidebar as a
modal navigation surface. `WorkspaceShell` owns the transient open state, makes both the skip link
and `.workspace-main` inert and hidden from assistive technology, preserves and locks the body
overflow value, focuses the first current drawer control, wraps forward and reverse Tab movement,
and restores focus only when the captured opener is still connected. The visual scrim remains a
pointer target but is removed from the accessibility tree and tab order because the drawer already
contains a labelled close control.

Close the drawer on Escape, a navigation action, a changed route, and a resize at or above the
existing 992 px desktop breakpoint. Cleanup on close or unmount removes listeners and restores
scroll state. The conditional sidebar role is `dialog` with `aria-modal=true` only while the mobile
drawer is open; its ordinary desktop `complementary` semantics remain unchanged. Existing global
`prefers-reduced-motion` rules cover both drawer and scrim transitions.

Focused React tests cover modal semantics, inert background, scroll locking and cleanup, both focus
wrap directions, Escape, focus restoration, route change and desktop resize. A dependency-free
Playwright harness loads the production CSS and checks 320, 375, 991 and 1,280 px geometry,
horizontal overflow and reduced-motion transition duration. The production entrypoint also drops
the Bootstrap JavaScript bundle after a repository-wide scan confirms there are no Bootstrap
plugin constructors or interactive `data-bs-*` attributes; Bootstrap CSS and the static dark-theme
attribute remain. Full frontend tests, lint and a production build prove the removal introduces no
runtime dependency. This is a clarification of Constitution VIII, advanced to version 1.1.5; it
does not change persistence, local inference, transport, permissions or network behavior.

### Phase Q — Measured offline renderer boot

Keep every supported language in the signed local distribution, but move English and Italian into
separate static modules behind a small registry that deduplicates concurrent imports. The
`I18nProvider` first loads only the locally selected catalogue, renders a bounded localized boot
state, falls back from Italian to English when possible and changes/persists the active language
only after the requested module resolves. While a user-initiated switch is pending, both controls
are disabled and the group reports busy state. If neither boot catalogue loads, replace loading
copy with a static English/Italian alert and an explicitly activated retry control that receives
focus; never reload or retry in a loop. Tests retain an eager bilingual aggregate exclusively for
catalogue parity and deterministic component setup, while production modules never import it.

Replace the Bootstrap Icons stylesheet and complete WOFF/WOFF2 font with a generated CSS mask
subset. A repository script scans every JavaScript/JSX source token, rejects computed or missing
`bi-*` names, embeds the corresponding MIT-licensed Bootstrap SVG and checks the generated file for
drift. This preserves `currentColor`, inherited icon sizing and the existing DOM while removing the
initial font request. Bootstrap CSS remains available to authenticated screens that use its grid,
forms, utilities, modal and spinner contracts, but is lazy-loaded only after a session is restored.

Move inactive language controls and login privacy copy from the faint token to the muted token,
increase both language targets to 44 CSS pixels, and retain the global three-pixel focus ring. A
real production-build Chromium test at 390 px verifies English, a live Italian switch and persisted
Italian, including one-locale loading, zero font requests, SVG-mask geometry, focus/disabled state,
WCAG contrast, axe and console/page errors.

Keep the meta CSP for offline/browser fallback protection but remove `frame-ancestors`, which
browsers do not enforce from a meta element. Preserve framing denial in Nginx response headers and
the native Tauri CSP, cover the delivery split with a Node contract test, and stop suppressing the
formerly expected browser warning in demo recording.

Run a post-build budget validator over the actual hashed distribution. It requires separate EN/IT
chunks, no Bootstrap icon font, an entry no larger than 350,000 raw/112,000 gzip bytes and
worst-case login resources no larger than 660,000 raw/185,000 gzip bytes. Separate ceilings cover
the selected locale, login CSS and lazy authenticated workspace CSS and shell chunks. Focused registry,
StrictMode, boot-failure, switch, login, distribution and browser tests precede the complete
frontend and repository release gates. The slice changes no API, persistence, inference, runtime
permission or remote-network boundary and clarifies Constitution VII and VIII at version 1.1.6.

As final distribution hardening, set Dependabot's default cooldown to seven days in all five
managed ecosystem entries while retaining its security-update exception. Put repository, tag and
commit context into workflow environment variables and quote them at release command boundaries;
never interpolate those GitHub values directly into shell arguments. Normalize the frontend
proxy's upstream Host to the backend allowlisted identity `localhost` rather than reflecting the
request Host. Static contract tests lock all three configuration boundaries.

### Phase R — Fail-closed local session and distribution boundary

Canonicalize runtime configuration before middleware is assembled: allow only development, test
or production, pin the private prefix to `/api/v1`, validate one exact canonical Host authority,
pin JWT signing to HS256, require a production signing-secret floor, and reject an
entire CORS allowlist if any origin is duplicated, wildcarded or carries credentials, non-root
path, query, fragment or unsupported scheme. Apply the same exactness to renderer API bases: the
browser uses `/api/v1`; desktop configuration uses that path on an HTTP(S) loopback origin only.

Respect bcrypt's 72-byte UTF-8 boundary in both registration schema and login transport before any
hash work, without truncation. Explicit logout invalidates renderer access immediately and unmounts
the private workspace, but a failed cookie-clearing request becomes a bilingual retry surface
instead of a false success or a newly exposed login form. Forced unauthorized cleanup remains
best-effort because the private renderer is already closed. Scope the refresh cookie to the auth
subtree and delete both narrow and historical root-path canonical/legacy variants during issuance,
rotation and logout; document that loopback ports are not independent browser cookie principals.

Remove dynamic backend API compression. Nginx compresses only public static assets, emits one
canonical no-store policy for every proxied API result, serves the SPA shell and unhashed public
assets with revalidation, and grants immutable caching only to Vite's fingerprinted `/assets/`
files. Container smoke tests measure gzip transfer budgets and assert cache-header cardinality,
while a response larger than 1,000 bytes proves the API remains uncompressed.

Move the full authenticated workspace, its search provider and Bootstrap CSS behind the successful
session branch. Group locale keys by namespace before reconstructing the identical frozen runtime
catalogue. This preserves all 1,524 keys in each language while reducing real initial transfer.
Ratcheted raw/gzip ceilings retain roughly 10–15% measured headroom for entry, locale, login CSS,
aggregate login resources and the authenticated workspace chunks. This phase clarifies
Constitution VII and VIII at version 1.1.7 without adding persistence, inference, permission or
network capabilities.

### Phase S — Stateful refresh rotation and replay containment

Add `AuthSession` as a content-free, per-account table with eight database-unique slots. Each row
stores a non-secret family id, SHA-256 digest of the only current refresh JTI, expiry and revocation
time. Login and registration allocate a slot; at capacity the oldest family is removed inside the
same transaction. Slot uniqueness makes concurrent allocation fail closed and bounded, with a
short retry against fresh state.

Require canonical claims on both access and refresh JWTs. Both carry the same `sid`; refresh
conditionally updates the current digest and commits before returning a new cookie. A losing
concurrent request or any older token observes a digest mismatch and revokes the family, including
the winner's new token. Access authorization binds its subject and `sid` to that live family row on
every protected request. Logout accepts the current or rotated token and revokes by its signed
account/family binding. A pre-migration token has no `sid`, fails validation and requires login;
invalid refresh cookies trigger the existing clear path.

Create one Alembic revision with an empty-table upgrade and drop-only downgrade. Raw tokens and
JTIs never enter persistence. Portable export remains unchanged and excludes the table; successful
restore revokes the restored account's families, while complete erasure deletes only owned rows.
Test real file-backed SQLite races, sequential replay, logout with an old token, bounded concurrent
allocation, migration cascade/round-trip and forced commit rollback. The renderer treats a 401 on
the post-refresh retry as terminal unauthorized state rather than leaving private UI mounted.

### Phase T — Live access-family authority and deterministic client sessions

Reuse `AuthSession.id` as the authority referenced by both access and refresh JWTs. Do not add an
access-token table, JTI blacklist or schema revision: the existing primary-key family row is enough.
Every protected request replaces the previous username-only lookup with one indexed join over
`AuthSession.id`, subject ownership, revocation and family expiry; JWT expiry remains independently
enforced by decode. This adds no database round trip relative to the previous dependency, but the
query now carries the explicit live-authority check. A committed logout, replay response, restore
or erasure therefore rejects every later protected request for that family. Requests already
authorized before the commit are outside retroactive cancellation.

Issue both bearers before committing one new family and rotate both with the same stable `sid`.
Generate all replacement credentials before the compare-and-swap so signing failure cannot consume
the current refresh token. Logout derives the union of valid cookie and bearer bindings, revokes all
of them in one transaction and never reports partial success. If commit fails, roll back, return a
sanitized `503`, clear HttpOnly refresh cookies so reload cannot resurrect the workspace, and retain
the access bearer only in renderer memory for an explicit retry. No raw bearer, refresh JTI or
access JTI enters persistence.

Make account transitions last-started-wins: login and registration invalidate the previous client
epoch before capture, and a late login, registration or refresh response cannot overwrite a newer
identity. When `Origin` is absent, reject auth mutations whose browser Fetch Metadata is anything
other than one `same-origin` value; native and CLI callers that omit both headers remain supported.
Pin Node to `>=24.18.0 <25`, enable npm engine strictness and put the same executable preflight in
front of every Node/Vite/Playwright/Tauri npm entry point. Test real refresh races, atomic logout
rollback/retry, restore and erasure invalidation, client overlap races, terminal second-`401`, every
auth mutation's origin matrix and both sides of the Node runtime floor.

### Phase U — Crash-recoverable vault lifecycle and bounded maintenance

Extend `User` through one Alembic revision with a constrained lifecycle state, nullable restore
fingerprint and indexed pending-state lookup. Keep normal authority limited to `ready`. Serialize
login issuance and lifecycle transitions on the owner row (`BEGIN IMMEDIATE` on SQLite, row locks
elsewhere), and repeat auth-family revocation immediately before reset/erasure completion so a
racing login cannot escape the maintenance boundary. Represent erasure recovery with a disposable
sentinel family that is usable only through a signed `vault_maintenance` access purpose; deleting
that sentinel on logout makes the presented bearer permanently invalid, while password login can
mint a replacement recovery authority. Never expose a refresh token for pending maintenance.

Put reset, restore and erasure behind one desktop maintenance mutex and a writer-priority activity
gate. Normal authenticated work holds a reader lease; queued writers deny new readers instead of
starving. Cancellation releases both layers. Keep liveness pure async, make readiness a try-read
that never waits behind a writer, and include the joined managed-runtime worker's real health.
During application teardown, stop the scheduler before background task snapshots/cancellation and
wait for managed startup/worker termination within the desktop's bounded sidecar drain contract.

Before restore publishes an absent managed file, persist redundant checksummed journal copies in
`.restore/user-{id}`. Journal only paths this restore can create, bind them to the verified archive
fingerprint and enforce monotonic path-superset generations. Stage bytes inside that owner tree,
fsync the file and destination directory, then atomically publish; use `MoveFileExW` with replace
and write-through flags on Windows. A restart retries only the same archive and clears staging;
complete erasure may supersede restore if the archive is lost. Cleanup queries current database
bindings first so a journaled content-addressed file acquired by another account is preserved.

Decode string primary keys as canonical lowercase hyphenated UUIDs and derive, rather than trust,
the exact asset, photo and resume storage layouts. On restore success revoke sessions and grants,
disable restored schedules and clear lifecycle state only in the committing transaction. On
failure, roll back, delete still-exclusive journal paths durably, remove the journal, checkpoint
and vacuum SQLite under secure-delete; if any cleanup step fails, preserve `restore_pending` and
return an actionable same-archive-retry-or-erasure response. At startup remove only `.write-*`
temporaries under managed `assets` and `resumes`, never other namespaces.

Bound the in-memory portability surface at 128 MiB compressed, 256 MiB expanded, 5,000 members and
100,000 records. Read source uploads only to the configured limit plus one byte and translate
parser failures into stable content-free diagnostics. Update constitution, specification, plan,
tasks, data model, OpenAPI, privacy and architecture documents, then record analysis and
convergence evidence. Gate the slice with migration downgrade refusal, auth races, recovery logout,
journal corruption/torn-write, hard-crash retry, lost-archive erasure, shared-reference rollback,
SQLite remnant sanitation, canonical-identity/path, writer/readiness, Windows replacement and
full lint, type, backend-test and Node-preflight runs.

### Phase V — Production boundary follow-up

Keep API loopback transport separate from links derived from provider, imported or portable data.
The renderer accepts only credential-free HTTPS destinations plus its separately validated mail
path, and Tauri grants the opener exactly the same scoped URL patterns. Job-Room requests validate
the exact configured HTTPS origin before network activity, ignore ambient proxy variables and stop
at redirects so an upstream response cannot create a second request to a local or unrelated host.

Make cancellation and recovery transitions explicit: a cancelled request stops waiting on a shared
refresh without cancelling surviving waiters, desktop readiness aborts both fetch and response-body
work, and full-screen recovery, logout and boot failures receive deterministic focus. Minimize the
managed model child environment, verify sidecar disappearance on every native smoke exit path, keep
Bootstrap in one lazy workspace-only stylesheet, and ratchet measured CSS budgets. Bound CI evidence
retention to seven days and release intermediates to fourteen days. Focused frontend, provider,
release, notice, Rust and production-build gates record the resulting evidence.

### Phase W — Renderer CSS delivery boundary

Treat unauthenticated lifecycle UI and the authenticated workspace as separate delivery surfaces.
The entry graph owns only the dark theme foundation, focus and form primitives, login, recovery,
localization, native boot and the exact lifecycle icon subset. `AuthenticatedWorkspace` owns the
complete auditable icon set, legacy styles, the established CareerOS stylesheet and the isolated
Bootstrap compatibility layer in that order. Retaining the complete stylesheet after the legacy
sheet preserves the existing workspace cascade, while the small critical copy prevents workspace
rules from entering the login request path.

Make the boundary executable rather than comment-only. The production validator requires one
initial and one lazy workspace stylesheet, rejects representative workspace selectors and the
Bootstrap layer from the former, requires lifecycle selectors and accessibility media there, and
requires workspace, print, forced-colors, reduced-motion and responsive contracts in the latter.
Generate a separate lifecycle icon subset from the lifecycle source graph, retain the complete
generated subset only in the lazy workspace, and ratchet raw/gzip budgets from a fresh supported
Node build. Gate the slice with full Vitest, lint, build, runtime/distribution contracts and real
Chromium login and workspace responsive checks.

### Phase X — Bounded transport, runtime and content-addressed persistence

Make the resource boundary precede every parser. A pure ASGI middleware counts streamed request
bytes and validates declared length before multipart work; Nginx retains the matching default cap.
Keep raw file, decoded text, PDF page, DOCX member/expansion, photo pixel/edge and portable archive
limits independently configurable only inside startup-validated hard ceilings. Split database-free
source parsing from persistence and run it, plus photo normalization, in the shared worker pool so
the event loop can answer pure liveness throughout hostile or expensive input processing.

Treat every remote provider and loopback inference response as an untrusted stream. Request identity
encoding, refuse redirects and compression, ignore proxy environment, cap declared and actual bytes,
and validate the full response shape before domain transforms. Validate all model, sampling,
timeout, context, token, provider pagination, workload and geospatial controls before network use.
Keep Job-Room session bootstrap single-flight and cancellation-clean.

Use the checksum-pinned managed-runtime archive as an ongoing trust root, not an installation-only
input. Follow only bounded, manually allowlisted release redirects; reject archive aliasing,
special files and both declared and observed expansion overflow; record and reverify every runtime
payload file. Recheck the GGUF and minimize the child process environment immediately before spawn.
Cancellation covers download, extraction, verification, installation, startup and shutdown, while
failed termination retains the process handle and a bounded restart policy prevents crash loops.

Publish content-addressed bytes with create-if-absent semantics. Serialize SQLite source and photo
file/row ownership with `BEGIN IMMEDIATE`, clean a newly created file before releasing a failed
transaction, and prepare successful response data before commit. Prove same-profile and
cross-profile convergence with real file-backed SQLite sessions, repeated thread races and shared
reference-aware deletion. Serialize resume version allocation under the same writer discipline,
journal prospective PDF/DOCX paths before publication and reconcile commit ambiguity, process loss,
draft deletion and complete erasure without deleting shared or committed bytes. Keep parsing,
normalized-photo and storage modules below the repository's focused-module size boundary. Record
exact focused and full lint, type, backend, frontend, distribution and real-browser evidence in
analysis and convergence artifacts.

## Complexity Tracking

| Violation | Why Needed During Migration | Required Resolution |
|-----------|-----------------------------|---------------------|
| Python sidecar adds a process boundary | Rewriting the mature persistence, rendering and workflow domain in Rust would destroy verified behavior and delay desktop delivery | Authenticate loopback, own lifecycle in Tauri, contract-test it, and keep transport replaceable |
| `backend/services/llm_service.py` is 1,896 lines | Existing tests and search consumers import this facade directly | Extract runtime policy, task prompts/contracts, normalization, matching and planning; leave a compatibility facade below 300 lines |
| `backend/services/search_service.py` is 2,986 lines | It coordinates an existing stateful pipeline with many tested transitions | Extract acquisition, catalog persistence, normalization, matching and finalization services; facade below 300 lines |
| `backend/services/search/listing_utils.py` is 1,501 lines | Legacy deterministic mappings are broad and provider-sensitive | Split by normalization domain and retain snapshot tests for mappings |
| Model/runtime acquired after installation | Bundling a 1.83 GB model makes downloads and updates unnecessarily large | Explicit consent, exact allowlisted URLs, displayed size/license, atomic SHA-256 verification and full offline operation afterward |
