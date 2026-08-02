# Feature Specification: CareerOS Local Desktop Career Agent

**Feature Branch**: `codex/001-desktop-career-agent`

**Created**: 2026-07-17

**Status**: Approved for planning

**Input**: Transform the project into CareerOS Local: an installable, distributable,
local-first desktop career agent with a detailed career vault, editable resume canvas,
ATS and photo resumes, career goals, and more accurate local AI on small models.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Install and own a private career workspace (Priority: P1)

A person downloads one installer, launches CareerOS Local like any other desktop
application, creates a private local vault, and can return to it without running developer
tools or creating a cloud account.

**Why this priority**: The application cannot be local-first or broadly usable while it
depends on a development environment, containers, or manually operated services.

**Independent Test**: Install on a clean supported desktop, create a profile, close the
application, reopen it offline, and confirm the same profile is available and no child
process remains after exit.

**Acceptance Scenarios**:

1. **Given** a clean supported computer, **When** the user completes installation and first
   launch, **Then** the application opens without requiring a shell, container engine,
   language runtime, API key, or online account.
2. **Given** an existing vault and no network connection, **When** the user restarts the
   application, **Then** all locally available non-network features and documents work.
3. **Given** the application is closed normally, **When** process state is inspected, **Then** the
   sidecar first receives a bounded graceful-shutdown request and FastAPI lifespan cleanup is
   allowed to stop managed local services. **Given** instead that the native parent disappears,
   **Then** the watchdog or operating-system containment applies a bounded fallback and no
   application-owned background service remains orphaned.
4. **Given** an application update, **When** it is installed, **Then** the vault is migrated
   safely and existing profile, job, application, goal and resume data remain available.
5. **Given** the authenticated workspace at a mobile width, **When** the navigation drawer opens,
   **Then** it is exposed as modal navigation, focus starts and remains inside it, the obscured
   workspace and skip link become inert, background scrolling stops, and Escape closes the drawer
   and restores focus. Activating a route or resizing to the desktop layout also closes the drawer
   without leaving scroll or accessibility state behind, and reduced-motion preferences suppress
   the drawer transition.
6. **Given** English or Italian is selected on the local login screen, **When** the packaged
   renderer starts offline, **Then** it loads only that bundled language catalogue, renders the
   complete icon interface without an application-wide icon font, stays inside the measured boot
   budgets and exposes no serious accessibility, contrast, keyboard-focus or CSP-console defect.
   Switching language loads the other bundled catalogue, disables duplicate switch actions while
   it is pending and persists the new choice only after the catalogue is ready. If neither the
   selected catalogue nor the English fallback can load, the loading state becomes a statically
   localized alert with a focused explicit retry and never starts an automatic reload loop.
7. **Given** an authenticated browser session, **When** its refresh token rotates, is replayed,
   races another refresh, is presented to logout, or predates the server-side session migration,
   **Then** exactly one current token can rotate, detected reuse revokes the whole bounded session
   family, every access bearer from that family immediately loses authority for new protected
   requests after committed revocation, logout removes every valid family presented by its cookie
   and bearer atomically, and invalid legacy cookies are cleared without exposing private content.

---

### User Story 2 - Build a complete career profile and direction (Priority: P1)

A person records a detailed career history, evidence, preferences, constraints and goals so
the agent has a single trustworthy source for resume generation, opportunity analysis and
career planning.

**Why this priority**: High-quality career assistance is impossible without structured,
complete and evidence-backed source data.

**Independent Test**: Create a profile containing contact preferences, work history,
achievements, skills with evidence, education, certifications, languages, projects,
volunteering, publications, preferences, constraints and goals; restart and verify that all
relationships and progress data remain intact.

**Acceptance Scenarios**:

1. **Given** an empty vault, **When** the user completes guided profile setup, **Then** the
   application shows completeness by section and identifies missing evidence without
   blocking partial progress.
2. **Given** a work achievement, **When** the user links it to a role, skills, metrics and
   source material, **Then** those relationships are visible and reusable by documents.
3. **Given** a career goal with target roles, location, compensation, timeline and skill
   gaps, **When** progress changes, **Then** the user can track milestones, actions and
   evidence against the goal.
4. **Given** conflicting or impossible dates, **When** the profile is saved, **Then** the
   application highlights the conflict and preserves the draft for correction.
5. **Given** a new local account and an existing CV, **When** the user chooses the CV-first
   setup path, **Then** CareerOS creates the minimum local Vault record before importing the
   document, keeps every extracted candidate unconfirmed, and takes the user to an explicit
   review step without requiring a model or developer tool.

---

### User Story 3 - Generate and manually refine truthful resumes (Priority: P1)

A person generates a role-targeted resume automatically from profile facts, chooses either
an ATS-safe layout or a visual layout with an optional photo, then adjusts content and layout
directly on a resume canvas before exporting.

**Why this priority**: Resume creation is the primary tangible outcome of the career agent,
and automatic generation must coexist with full user control.

**Independent Test**: Generate both resume variants from one profile, drag/reorder and edit
sections on the canvas, undo and redo changes, save a version, export it, and verify every
claim maps back to profile evidence.

**Acceptance Scenarios**:

1. **Given** a sufficiently complete profile and target role, **When** automatic generation
   runs, **Then** the draft selects relevant supported facts and contains no unsupported claim.
2. **Given** an ATS resume, **When** it is exported, **Then** it is single-column, contains no
   photo, and its headings and text remain extractable in reading order.
3. **Given** a visual resume, **When** the user adds a photo, **Then** metadata is removed and
   a readable photo-free fallback remains available.
4. **Given** a generated draft, **When** the user edits text, reorders sections, resizes
   blocks, changes allowed styles, or hides an item, **Then** the canvas updates immediately,
   records undo history and preserves a non-destructive saved version.
5. **Given** content that exceeds a page boundary, **When** the layout is previewed or
   exported, **Then** overflow is visible before export and the application proposes safe
   corrections without silently deleting content.

---

### User Story 4 - Receive accurate help from small local models (Priority: P2)

A person installs or selects a compact local model and uses it for profile extraction,
job normalization, opportunity matching, resume tailoring and career recommendations while
seeing sources, confidence and validation status.

**Why this priority**: Local inference must remain useful on ordinary hardware; accuracy and
transparency matter more than model size or persuasive prose.

**Independent Test**: Run the versioned offline evaluation set with the minimum supported
model profile and verify structured validity, evidence coverage, hallucination and task
accuracy thresholds; then repeat a user workflow with networking disabled.

**Acceptance Scenarios**:

1. **Given** no ready local model, **When** an AI-assisted action or opportunity-analysis
   workflow is requested, **Then** the application blocks that action, explains the failed
   prerequisite and opens an explicit local-model setup and readiness path while preserving
   deterministic non-AI functionality.
2. **Given** an installed supported model and an offline computer, **When** an AI task runs,
   **Then** all inputs and outputs remain local and the result identifies supporting facts.
3. **Given** malformed, contradictory or unsupported model output, **When** validation runs,
   **Then** the result is rejected or repaired within a bounded attempt count and never
   silently becomes trusted data.
4. **Given** a low-confidence recommendation, **When** it is shown, **Then** uncertainty and
   missing evidence are clear and the user can accept, edit or discard it.
5. **Given** a long profile and job description, **When** a compact model is used, **Then**
   the selected context contains only relevant, attributable information and preserves the
   facts needed for the requested task.

---

### User Story 5 - Carry, recover and erase the career vault (Priority: P2)

A person exports a complete portable backup, restores it on another installation, and can
permanently erase local career data without contacting a service provider.

**Why this priority**: Local ownership requires recovery, mobility and deletion rather than
mere on-device storage.

**Independent Test**: Export a populated vault, restore it into a fresh installation,
compare all entity counts and document hashes, then invoke deletion and verify no vault or
temporary document content remains in application-managed storage.

**Acceptance Scenarios**:

1. **Given** a populated vault, **When** the user exports a backup, **Then** the result includes
   profile data, relationships, goals, jobs, applications, resume versions, attachments and
   a machine-readable manifest.
2. **Given** a valid backup from a supported version, **When** it is restored, **Then** the
   application validates integrity before changing the active vault and reports the outcome.
3. **Given** a damaged or incompatible backup, **When** restore is attempted, **Then** the
   active vault is unchanged and the problem is actionable.
4. **Given** explicit deletion confirmation, **When** local erasure completes, **Then** the
   application removes its vault, generated documents and sensitive temporary files while
   leaving unrelated user files untouched.
5. **Given** reset, restore or erasure is killed after its first mutation, **When** CareerOS
   restarts, **Then** normal workspace access remains blocked and the user sees only the matching
   password-protected recovery action.
6. **Given** a restore published one managed file before process loss, **When** the same verified
   archive is retried, **Then** restore resumes without conflict; **When** that archive is no
   longer available, **Then** complete erasure can remove the pending data and recovery staging.
7. **Given** a crashed restore published content that another local account subsequently bound,
   **When** the first restore rolls back or erases, **Then** the shared file remains intact for the
   account that still references it.
8. **Given** the user logs out while complete erasure is pending, **When** the old recovery bearer
   is presented, **Then** it is rejected; a correct-password login returns a new maintenance-only
   authority without exposing the ordinary workspace.

---

### User Story 6 - Verify an application pack before sending (Priority: P1)

A person opens a saved application and sees a plain, evidence-based readiness audit covering
the captured role, contact route, career profile, linked resume version, exported documents and
resume evidence. They can export the same audit as Markdown or JSON for their own records.

**Why this priority**: A pipeline is useful only when it helps the user take the next concrete
step. A deterministic preflight catches missing material without asking the user to trust an AI
opinion or send private career data elsewhere.

**Independent Test**: Create an incomplete manual application and verify its blocker list, then
add a complete profile and a current published resume with artifacts, link it to the application,
and verify that the report, score, fingerprint and exported bytes are stable for the same state.

**Acceptance Scenarios**:

1. **Given** an application without a full role description, application route, profile or linked
   resume, **When** readiness is opened, **Then** each missing input appears as a separate blocker
   with a direct corrective action that opens the relevant application form, Career Vault or
   Resume Studio workflow.
2. **Given** a linked published resume, **When** readiness is computed, **Then** CareerOS checks
   ownership, safely contained readable artifact bytes, immutable digest and byte-size integrity,
   publication quality, profile revision and selected-fact verification without invoking a model.
3. **Given** the same vault state, **When** JSON or Markdown is exported more than once, **Then**
   the bytes and SHA-256 digest are identical and contain no access token or filesystem path.
4. **Given** a user who works offline or has no local model installed, **When** the report is
   inspected or exported, **Then** the complete workflow remains available.
5. **Given** a recorded resume artifact that is missing, unreadable, corrupt or resolves outside
   the vault data root, **When** readiness is computed, **Then** that format is not counted as
   available and the report blocks sending until the resume is republished.
6. **Given** the application drawer is opened from a board card, **When** the user navigates by
   keyboard or opens the dynamic preparation editor, **Then** focus remains inside the labelled
   modal, Escape closes it, obscured workspace controls cannot receive focus or scroll, and focus
   returns to the opening card.

---

### User Story 7 - Run applications as a private daily workflow (Priority: P1)

A person can discover a role from an explicit brief or capture it manually, then keep a dated next
action and publish a verifiable application dossier with every requirement, answer and checklist
item represented. Manual capture, application management and dossier publication remain complete
without a model; opportunity discovery requires validated local-model analysis.

**Why this priority**: A useful local career utility must preserve privacy and intent at ingestion,
survive concurrent edits, and export the exact application material the user reviewed.

**Independent Test**: Disable deterministic query classes with zero limits, save the same manual
listing as two users, race two stage updates at the same revision, reorder task event timestamps,
and publish a multi-row dossier. Verify isolation, one CAS winner, max-revision replay, projection-
only board reads and lossless payloads.

**Acceptance Scenarios**:

1. **Given** a manual listing with a client-supplied platform id, **When** it is saved repeatedly by
   one user and then by another, **Then** the client id is ignored, the same-user retry returns the
   same job, and each user has a distinct private listing row.
2. **Given** explicit role and strategy input and a ready local model, **When** provider search
   runs, **Then** the planner uses only those inputs and explicit preferences, never calls the
   model, rejects legacy/model-derived cache entries, keeps CV text and normalized fields behind
   the provider boundary, treats zero as disabled and `NULL` as the local default, and persists a
   match only after validated local-model analysis.
3. **Given** two sessions at the same application revision, **When** both append a stage event,
   **Then** exactly one conditional update and event commit; the other receives a conflict.
4. **Given** task events whose user-controlled occurrence timestamps are out of order, **When** the
   detail timeline is replayed, **Then** the highest coherent contiguous revision wins and
   regressive or conflicting duplicate histories are rejected.
5. **Given** the application board is loaded, **When** a next action is shown, **Then** one narrow,
   deterministically ordered SQL query reads transactionally maintained scalar projections without
   selecting `job_snapshot`, events or dossier payloads.
6. **Given** multiple requirements, questions, answers and checklist items, **When** a dossier is
   published, **Then** every complete row is preserved, partial question-answer pairs produce a
   visible error, evidence ids are valid UUIDs, fact snapshots are deduplicated in a bounded catalog,
   archive/event sizes are preflighted, and add/remove controls have accessible names.
7. **Given** an incomplete dossier in progress, **When** the user edits, closes, reopens, encounters
   a failed save or races another editor, **Then** one bounded private draft is restored from the
   local vault, stable row identities remain unique, stale writes fail without clearing the form,
   and workspace publication consumes only the exact saved revision in the event transaction.

---

### User Story 8 - Start from one private daily action agenda (Priority: P1)

A person opens Applications and immediately sees the most useful next moves across the whole
pipeline: overdue work, work due today, upcoming deadlines, undated tasks and active applications
that do not yet have a next action. The agenda is a deterministic local read model and does not
require or imitate AI analysis.

**Why this priority**: Per-application tasks are durable, but a daily utility must answer “what do
I need to do next?” without making the user inspect every board column and dialog.

**Independent Test**: Create applications for two users with overdue, today, upcoming, later,
undated and absent next actions. Request one user's agenda with a DST-correct next-local-midnight
instant and horizon; verify exact classification and order, one-snapshot counts and rows, no
foreign records or event payload reads, explicit later/truncation counts, timed/focus refresh and
keyboard access from each agenda row to the owned application dialog.

**Acceptance Scenarios**:

1. **Given** active applications with projected next actions, **When** the agenda is requested,
   **Then** it classifies them as overdue, due today, upcoming or undated using one explicit UTC
   instant, the browser-calculated timezone-aware next local midnight and a bounded horizon.
2. **Given** an active application without a projected next action, **When** the agenda is loaded,
   **Then** it appears as needing an action, ordered from the least recently touched application.
3. **Given** actions beyond the horizon or more visible rows than the requested limit, **When** the
   agenda is returned, **Then** it reports the omitted-later count and truncation count rather than
   implying that no other work exists.
4. **Given** another local account with its own applications, **When** the current user opens the
   agenda, **Then** no foreign role, company, task identifier, title or timing is returned.
5. **Given** the local model is unavailable, **When** the agenda is opened, **Then** classification,
   board navigation and manual task editing remain available because no analysis claim is made.
6. **Given** an agenda read while an application writer commits, **When** the response is built,
   **Then** counts and returned rows describe the same SQL-statement snapshot.
7. **Given** a visible Applications page, **When** the next deadline or local midnight passes, the
   window regains focus, or a hidden document becomes visible, **Then** the agenda refreshes once
   without leaking timers or retaining obsolete requests.
8. **Given** a 320 px viewport or keyboard/screen-reader navigation, **When** agenda content is
   inspected, **Then** functional text meets WCAG AA contrast, visible labels/descriptions are
   programmatically associated, and row content does not overlap or create horizontal scrolling.

---

### User Story 10 - Operate CareerOS safely from a coding agent (Priority: P2)

A person can let Codex, Claude Code or another MCP client perform the same normal career work they
can perform in the CareerOS workspace: configure job providers, search and analyze opportunities,
maintain the Career Vault, prepare truthful resume and application materials, manage application
tasks and record application progress. The person chooses granular read, write and execution
scopes and a lifetime, receives one revocable bearer token, and acknowledges that the connected
agent may pass returned data to its own provider.

**Why this priority**: Application work spans discovery, analysis, tailoring and follow-up. A typed
operational boundary lets an agent complete that workflow while preserving CareerOS ownership,
evidence, revision and local-model gates; giving it the vault file, a desktop session token,
arbitrary filesystem access or a generic database command would bypass those guarantees.

**Independent Test**: Create two local users and grants with different scope sets. Through the
official MCP client over a real stdio subprocess, configure and test a declarative provider, run a
search, inspect verified analysis, generate a resume, create a dossier, move an application to
`applied` and add a follow-up task. Verify exact tool discovery, scope enforcement, user isolation,
revision conflicts, local-model fail-closed behavior, bounded typed results, stdout protocol
purity, credential redaction, revocation and expiry. Keep the desktop process open for a second run
and verify that automation fails with `vault_busy` instead of becoming a concurrent writer.

**Acceptance Scenarios**:

1. **Given** an existing local account and a closed desktop app, **When** the user runs
   `careeros authorize`, authenticates interactively and selects a lifetime and at least one
   explicit scope, **Then**
   CareerOS returns a random bearer token once and persists only its SHA-256 digest, account
   binding, label, scopes, expiry and revocation state.
2. **Given** a grant with only `applications:read`, **When** an MCP session starts, **Then** only
   application read tools are registered and a direct attempt to call a mutation or another
   domain facade fails with `scope_denied`.
3. **Given** a grant with the corresponding read and write scopes, **When** the agent configures a
   JSON or HTML job provider, searches, reviews verified job analysis, generates and publishes a
   truthful resume, creates an application dossier and records `applied`, **Then** every result is
   user-scoped, revisioned and equivalent to the corresponding desktop-domain operation.
4. **Given** CareerOS Local is already running, **When** a CLI command or MCP tool call tries to
   access the vault, **Then** it fails with `vault_busy`. **Given** an idle MCP server, **When** the
   desktop opens, **Then** it may own the vault until it closes; MCP reacquires the lease before
   the next read and never becomes a concurrent writer.
5. **Given** a missing, expired, revoked, malformed or foreign token, **When** a read is attempted,
   **Then** no facade is created and the process returns a stable content-free authorization error.
6. **Given** the disclosure flag is absent, **When** the MCP server is started, **Then** it refuses
   to run and explains that a connected agent may transmit tool results to its provider.
7. **Given** a valid scoped grant, **When** the user lists or revokes it, **Then** CareerOS requires
   the account password again and never prints the bearer token.
8. **Given** a vault restore or complete erasure, **When** the operation commits, **Then** active
   automation grants are revoked or removed so a token from the previous vault state cannot be
   reused.
9. **Given** an authenticated desktop user, **When** they create a grant from Agent Access,
   re-enter the current password, select at least one scope and choose a bounded lifetime,
   **Then** the local API returns the bearer once with `Cache-Control: no-store`, the interface
   labels it as a one-time secret, and later grant lists contain metadata only.
10. **Given** a visible one-time bearer, **When** the user copies it explicitly, dismisses it,
    signs out or leaves Agent Access, **Then** CareerOS performs no automatic clipboard or browser-
    storage write and removes the bearer from renderer state. Listing remains usable if issuance
    fails, and revoking an owned active grant requires the current password again.
11. **Given** a provider configuration containing an HTTP URL, a private or loopback destination,
    a redirect, an unbounded response, executable code or an invalid extraction rule, **When** it
    is saved or tested, **Then** CareerOS rejects it before expanding network authority or parsing
    the response and returns no stored secret value.
12. **Given** two agent mutations derived from the same revision, **When** both are attempted,
    **Then** one may commit and the stale operation receives a conflict that requires an explicit
    reread; no last-write-wins path bypasses the domain service.
13. **Given** a new or upgraded vault with no imported provider rows, **When** the desktop or MCP
    starts, **Then** no network provider is installed, enabled or constructed and the Providers
    workspace explains how to create or import one.
14. **Given** the external Swiss provider pack, **When** the user or a `providers:write` agent
    explicitly imports it, **Then** its reviewed native adapters and declarative canton and niche
    sources become owned revisioned installations but perform no request until a separate explicit
    activation or an import with `activate=true` succeeds.
15. **Given** a provider document or pack containing unknown native adapters, executable fields,
    credentials, duplicate keys, an oversized collection or one invalid declaration, **When** it
    is imported, **Then** the complete import fails without creating or changing any provider.

### Edge Cases

- Disk space becomes insufficient during model acquisition, migration, backup or export.
- The application loses power while saving a profile, resume version or migration.
- A model process crashes, hangs, returns invalid text or exceeds its time budget.
- Two application instances attempt to open the same vault.
- Imported dates are partial, ambiguous, overlapping or in different calendar formats.
- The user has no quantified achievements, incomplete history or intentional career gaps.
- A photo has orientation metadata, transparency, an unsupported format or excessive size.
- A resume contains an unbreakable block, a very long URL or non-Latin text.
- A job source is unavailable while all local workflows must continue to work.
- Security software quarantines one packaged child executable.
- An update is interrupted after backup but before migration completes.
- The user selects a model that cannot satisfy the required structured-output contract.
- GitHub accepts a release upload but the client loses the response before recording success.
- A stale or foreign draft already uses the intended version tag, or duplicate drafts are visible
  only on a later release-inventory page.
- A platform packager emits whitespace, control characters or case-colliding filenames that a
  release host would normalize differently from the local checksum inventory.
- The default branch advances while a signed version tag and its release candidate are being
  verified.
- A resume artifact database row outlives a deleted file, points through a path escape or no longer
  matches its immutable digest or declared byte length.
- The application preparation editor adds focusable controls after the surrounding drawer opens.
- An automation grant expires during an MCP session or is revoked before the next tool call.
- The desktop app and an automation process race to acquire the same vault lease.
- A developer starts a read command against a vault whose schema is behind the current Alembic head.
- A connected agent provider has different retention or training terms from CareerOS itself.
- Two tabs or processes submit the same refresh token concurrently and one response arrives late.
- An upgrade leaves a signed pre-migration refresh JWT in the browser without a session-family id.
- Persistence fails after a refresh digest is conditionally replaced but before commit.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The product MUST be installable and launchable as a desktop application on
  supported Windows, macOS and Linux systems without developer tooling.
- **FR-002**: The desktop application MUST own startup, health monitoring, restart limits and
  shutdown of every packaged service and local model process it starts. A normal native exit MUST
  first request sidecar shutdown through the per-launch token-authenticated loopback API, prevent
  the shell from exiting while the sidecar drains, and wait only for a fixed upper bound. The
  sidecar MUST run FastAPI lifespan cleanup before exit when recovery remains possible. Parent
  disappearance MUST request the same graceful path through a watchdog before its own hard timeout
  unless operating-system containment has already terminated the process tree. A failed drain MUST
  fall back to direct termination; on Windows the sidecar and descendants MUST be contained by a
  kill-on-close Job Object so abrupt parent death or a wedged runtime cannot leave an orphan.
- **FR-003**: The product MUST provide clear install, upgrade and uninstall behavior that does
  not erase the career vault unless the user explicitly requests data removal.
- **FR-004**: The product MUST remain fully usable offline after required local components and
  a chosen model are installed, except for explicitly network-dependent job-source actions.
- **FR-005**: The product MUST NOT offer, contain or silently fall back to remote AI inference.
- **FR-006**: Model acquisition MUST require an explicit user action and show model size,
  hardware expectations, license, source, integrity status and disk location.
- **FR-007**: The user MUST be able to pause, cancel, retry, replace and remove a local model.
- **FR-008**: The user MUST be able to create and edit a structured profile covering identity
  and contact preferences, summary, roles, achievements, skills, projects, education,
  certifications, languages, publications, awards, volunteering, memberships, references,
  portfolios, work authorization, availability, compensation, location and work preferences.
- **FR-009**: Every reusable career fact MUST retain provenance, confidence, verification
  state, visibility, date range and relationships to relevant profile entities.
- **FR-010**: The product MUST validate temporal consistency and highlight gaps, overlaps,
  duplicates and unresolved conflicts without discarding user drafts.
- **FR-011**: The user MUST be able to define multiple career goals with target roles,
  industries, locations, work modes, compensation, deadlines, priorities and constraints.
- **FR-012**: Career goals MUST support milestones, actions, progress, skill-gap evidence and
  links to jobs, applications, learning activities and resume versions.
- **FR-013**: The user MUST be able to import career material locally, review extracted facts
  before acceptance and trace accepted facts back to their sources.
- **FR-014**: The product MUST generate a resume draft automatically from verified profile
  facts and a selected target role or opportunity.
- **FR-015**: Every generated resume claim MUST reference supporting career facts and the
  product MUST reject unsupported claims before saving a trusted version.
- **FR-016**: The product MUST provide an ATS-safe, single-column, photo-free resume variant
  with predictable reading order and text extraction.
- **FR-017**: The product MUST provide visual resume variants that may include a user-selected
  photo while retaining readable color-independent output and a photo-free alternative.
- **FR-018**: Imported photos MUST be processed locally, stripped of metadata and stored only
  within the user's vault or selected export destination.
- **FR-019**: The resume canvas MUST support direct text editing, section and item reordering,
  visibility controls, bounded resizing, approved style controls, zoom, page guides and
  keyboard-accessible operations.
- **FR-020**: Canvas edits MUST support undo, redo, autosave, explicit version naming,
  comparison and restoration without overwriting older versions.
- **FR-021**: The product MUST show overflow, unsupported layout and missing-content warnings
  before export and MUST never silently truncate user content.
- **FR-022**: Resume exports MUST be generated locally in PDF and editable document formats
  and validated for non-empty text, required sections, reading order and page overflow.
- **FR-023**: Local AI tasks MUST use bounded task-specific inputs, explicit output contracts
  and deterministic validation before results can update trusted records.
- **FR-024**: AI-assisted results MUST expose supporting fact references, confidence,
  validation status and material omissions in language understandable to the user.
- **FR-025**: Invalid AI output MUST be rejected or retried only within a visible bounded
  policy; repeated failure MUST return control without corrupting the active vault.
- **FR-026**: The product MUST preserve useful deterministic behavior when no model is
  installed or an AI task is unavailable, but MUST NOT label, persist or display that behavior
  as completed AI analysis, matching, tailoring, coaching or recommendation output.
- **FR-027**: The product MUST include a versioned offline evaluation set representative of
  profile extraction, job normalization, matching, resume tailoring and recommendation tasks.
- **FR-028**: Evaluation results MUST identify the application version, model profile,
  dataset version, task metrics, latency and peak memory without storing private user content.
- **FR-029**: The user MUST explicitly enable each network-capable job source and be able to
  disable all source access independently of local AI.
- **FR-030**: The user MUST be able to export, validate, restore and inspect a complete portable
  career-vault backup without a cloud service.
- **FR-031**: The product MUST protect the active vault from partial restore, interrupted
  migration and concurrent writers, and provide actionable recovery guidance.
- **FR-032**: The user MUST be able to erase application-managed career data and sensitive
  temporary files through an explicit confirmation flow.
- **FR-033**: Diagnostic logs MUST exclude document bodies, profile content, prompts, model
  output, contact details and secrets while still reporting operation and failure classes.
- **FR-034**: Release downloads MUST include version, platform, architecture, integrity
  checksum and software inventory; signing status MUST be stated accurately.
- **FR-035**: Core setup, profile, goal, resume-canvas, export, model and recovery workflows
  MUST be usable by keyboard with visible focus and actionable errors.
- **FR-036**: The product MUST present English on first launch and allow the user to switch
  the core shell, login and portfolio-demo workflows to Italian without a network request;
  the explicit choice MUST remain on the same device and update the document language.
- **FR-037**: A stable release MUST originate from a GitHub-verified annotated version tag whose
  recursively resolved commit matches the workflow source and remains contained in the current
  default branch before any release state is created or changed.
- **FR-038**: Every release asset MUST use a deterministic portable filename, appear in an exact
  target/type/name/size/SHA-256 manifest, retain that same name in downloadable checksum files,
  and carry verified GitHub-hosted build provenance for the exact tag, commit and workflow. Any
  declared SPDX license MUST be a first-class checksummed release asset bound to the approved
  canonical content. Every native installer or disk image MUST contain that exact project license,
  and package smoke verification MUST inspect the installed, extracted or mounted bytes before the
  package can be staged.
- **FR-039**: Release publication MUST be contract-bound, paginated, least-privilege and
  idempotent. It MUST reject duplicate, foreign or stale state; recover safely from ambiguous
  create/upload/publish responses; and finish only after the exact release ID, target commit,
  immutable/latest state and complete remote asset inventory are verified. Manual rehearsals
  MUST NOT receive OIDC/attestation/publication permissions or mutate tags, attestations or
  Releases. Tag publication runs MUST share one concurrency group with cancellation disabled for
  the running tag, and the publisher MUST rediscover the release sequence immediately before
  promotion.
- **FR-040**: Every application MUST expose a deterministic readiness report composed from the
  user's local application snapshot, profile and owned immutable resume version; no AI runtime or
  network access may participate in the calculation.
- **FR-041**: A readiness report MUST expose stable check identifiers, pass/warning/blocker state,
  score contribution, corrective action, source revision and a canonical SHA-256 fingerprint.
- **FR-042**: Readiness MUST verify role identity and detail, an application route, profile
  availability, linked resume ownership, safely contained readable rendered-artifact bytes against
  their immutable SHA-256 digest and declared length, publication validation, profile revision
  freshness and selected-fact verification. Artifact metadata without verified bytes MUST NOT pass.
- **FR-043**: The user MUST be able to download canonical JSON and human-readable Markdown
  readiness reports whose bytes are reproducible for unchanged state and contain neither local
  storage paths nor authentication material.
- **FR-044**: The user MUST be able to update the captured role title, company, description,
  application URL, application email and linked owned resume version without recreating the
  application. The write MUST require the expected application revision, reject stale writers and
  append a content-free audit event identifying only the changed field names.
- **FR-045**: Application Detail MUST be exposed as a labelled modal dialog that locks background
  scrolling, makes obscured workspace content inert, contains focus across dynamically inserted
  controls, closes with Escape and restores focus to the control that opened it.
- **FR-046**: Manual listing imports MUST ignore client-supplied ids for the `manual` platform,
  derive a stable opaque identifier from the authenticated user namespace and listing identity,
  return the existing same-user relationship on retry, and never share a manual row across users.
- **FR-047**: Deterministic planning MUST use only the user-entered role description, search strategy
  and explicit preferences. It MUST NOT mine CV text, LLM-normalized fields or unconfirmed intent;
  zero query limits disable and `NULL` query limits select configured defaults.
- **FR-048**: Every application event append MUST advance the expected revision through one
  conditional update that includes the resulting stage; a stale concurrent writer MUST append no
  event and receive a conflict.
- **FR-049**: Task replay MUST select the highest coherent revision per task independently of event
  occurrence order and reject missing, regressive or conflicting duplicate revisions. Application
  board reads MUST use the maintained next-action projection without replaying task events.
- **FR-050**: Dossier input MUST accept repeatable requirement/evidence, question/answer and
  checklist rows, preserve every complete row, report partial pairs without clearing draft input,
  use accessible add/remove controls, and validate evidence references as UUIDs.
- **FR-051**: Manual import and dossier schemas MUST reject unknown fields and enforce bounded text,
  collection and metadata sizes before domain services execute.
- **FR-052**: AI analysis is a required capability of CareerOS. The authenticated workspace MUST
  expose a blocking, keyboard-accessible local-model onboarding and structured-output readiness
  check before analysis workflows become available, without blocking Vault editing, portability,
  deterministic application readiness or existing document access.
- **FR-053**: Opportunity matching MUST persist a result only after a local model returns output
  that passes the declared structured contract. Runtime, timeout, circuit-breaker, schema or
  evidence failure MUST fail the analysis batch with an actionable status and MUST NOT invoke a
  deterministic scoring fallback.
- **FR-054**: Model readiness diagnostics MUST verify the configured endpoint privacy boundary,
  runtime reachability, configured-model availability and one content-free schema-constrained
  inference. Diagnostics MUST expose stable codes without logging prompts, model output, user data
  or secrets and MUST accept only the managed authenticated loopback runtime or the explicit local
  development allowlist.
- **FR-055**: Applications MUST expose a user-scoped daily agenda derived only from scalar
  application and next-action projections. It MUST classify overdue, local-today, upcoming,
  undated and missing-action work deterministically without replaying application event payloads
  or invoking a model. Counts and rows MUST be produced by one SQL-statement snapshot.
- **FR-056**: Agenda queries MUST accept only a validated timezone-aware next-local-midnight
  instant, bounded horizon and bounded result limit, exclude closed applications, return stable
  priority/deadline ordering, and expose active, later, visible and truncated counts so omitted
  work cannot be mistaken for an empty queue.
- **FR-057**: The Applications interface MUST present the agenda as keyboard-operable controls,
  preserve access to the full board when agenda loading fails, and open an owned application using
  the existing labelled, focus-contained detail dialog. It MUST refresh on focus, visible-state
  restoration, the next returned deadline and local midnight; clear obsolete requests and timers;
  associate visible heading/description text; and avoid overlap at 320 px with WCAG AA functional
  text contrast.
- **FR-058**: An authenticated user MUST be able to inspect a bounded portable archive without
  changing the active vault, even when that vault is populated. Inspection MUST validate archive
  structure, compatibility, member digests, typed records, relationships, application projections
  and persisted-file bindings; return only version, timestamps, digests, counts, byte totals and
  stable content-free codes; and report separately whether the current vault can accept a restore.
- **FR-059**: The desktop backup save flow MUST write to an isolated temporary sibling, verify the
  selected archive against the server-issued SHA-256 digest, replace the destination with rollback
  on failure where the filesystem permits, clean managed temporary files, and describe the backup
  as verified only after the final destination bytes have been re-read successfully.
- **FR-060**: Backup copy MUST state that the current portable ZIP is neither encrypted nor
  authenticated and that imported AI analysis or coaching output requires fresh local-model
  validation. Restore MUST remain a separate explicit action and MUST still require an empty vault.
- **FR-061**: A source-installed command MUST expose typed CareerOS operations to a human CLI and
  an MCP server over standard input/output. MCP MUST open no network listener and MUST expose
  normal career, resume, job, provider, search and application workflows only through bounded
  domain operations; it MUST expose no generic prompt, SQL, filesystem, credential, export,
  restore or erasure operation.
- **FR-062**: Automation authorization MUST require an interactive CareerOS password check and
  create a grant for exactly one local user with a bounded lifetime and an explicit subset of
  `system:read`, `career:read`, `career:write`, `resume:read`, `resume:write`, `jobs:read`,
  `jobs:write`, `search:execute`, `providers:read`, `providers:write`, `applications:read` and
  `applications:write`. The bearer token MUST be returned once; only a cryptographic digest and
  non-secret grant metadata may be persisted.
- **FR-063**: Every CLI data access, MCP bootstrap and MCP tool call MUST hold the existing exclusive
  desktop vault lease for that operation. MCP MUST release the lease while idle, then reacquire it
  and revalidate the grant before every tool call. Ordinary operations MUST reject an outdated
  schema without migration; only explicit authorization may migrate while the desktop is closed.
- **FR-064**: MCP MUST register only the tools allowed by the authenticated grant. Every tool
  result and input MUST use a bounded typed contract and disclose only fields needed by an
  authorized domain operation. Source-document bytes, prompts, artifact bytes, tokens, stored
  provider secrets and local storage paths MUST remain excluded. Mutations MUST call the same
  user-scoped domain services, revision checks, evidence validation and local-model readiness gates
  as the desktop. Scope checks in the service MUST remain authoritative even if client-side tool
  annotations are ignored.
- **FR-065**: MCP startup MUST require an explicit acknowledgement that a connected agent may
  transmit returned metadata outside the device. Documentation MUST distinguish CareerOS's
  no-egress stdio server from the separate privacy policy of the connected client and provider.
- **FR-066**: Users MUST be able to list and revoke their grants after another password check.
  If the desktop management route is already in an issuance lockout, it MUST NOT inspect further
  passwords and MAY only revoke a grant owned by the authenticated account.
  Restore MUST revoke active automation grants and complete vault erasure MUST delete them.
- **FR-067**: Every successful provider observation MUST refresh the canonical listing before
  per-profile deduplication. Listings MUST retain first-seen, last-seen, last-content-change and
  monotonic content-revision metadata. Identical observations MUST advance only last-seen time;
  canonical content changes MUST advance the revision, invalidate prior analysis through its input
  fingerprint and make the listing eligible for fresh local analysis without changing user
  decisions, applications or immutable application snapshots.
- **FR-068**: CareerOS MUST NOT infer that a listing is closed from its absence in a provider page,
  a failed or partial provider response, or a search with different criteria. Migration of existing
  listings MUST use a conservative revision-1 backfill and MUST NOT manufacture historical
  observations or content-change events.
- **FR-069**: Completing a search with terminal state `done` MUST atomically persist a durable,
  idempotent receipt on the owned search profile. The receipt MUST retain UTC start and completion
  times, the fixed state `done`, a monotonic successful-run count, and a bounded fixed-shape summary
  containing only aggregate counters, duration and aggregate provider outcome.
- **FR-070**: Failed, stopped and cancelled searches MUST NOT clear the latest successful receipt or
  increment its run count. Runtime-status pruning MUST leave the receipt intact. The summary MUST
  exclude CV content, query text, listing text, logs, error/provider bodies and credentials; profile
  create/update requests MUST NOT be able to write receipt fields. Portable restore MUST preserve
  valid receipts while canonicalizing away unknown JSON keys.
- **FR-071**: Every Job response MUST expose the current user's Application identifier and stage
  for the same logical opportunity, resolving duplicate Job rows through `scraped_job_id` without
  exposing another user's Application. Paginated Job responses MUST count distinct tracked logical
  opportunities independently of page size and without per-row queries.
- **FR-072**: A user MUST have at most one Application per Job-backed logical opportunity.
  Application creation MUST reject a duplicate reached through another search profile. Crossing
  the applied milestone MUST monotonically synchronize every duplicate Job's legacy applied marker;
  saved or preparing alone MUST NOT set it, and later withdrawal or archival MUST NOT clear it. The
  database MUST enforce uniqueness on the user and shared scraped-listing identity, including
  concurrent creation attempts. Migration and portable restore MUST preserve conflicting legacy
  timelines while assigning the unique logical identity only to the deterministically most recently
  updated timeline.
- **FR-073**: The legacy Job interaction PATCH MUST remain compatible and be documented as
  deprecated. Changing its applied marker MUST NOT implicitly create an Application, and it MUST
  NOT clear a marker backed by an Application timeline that has crossed the applied milestone.
- **FR-074**: Profile selectors and workspace setup status MUST use an authenticated, ordered,
  explicitly paginated allowlist projection rather than full search-profile records. The projection
  MUST exclude CV text, caches and normalized candidate payloads. Its aggregate MUST cover every
  profile owned by the user, independently of page size, and expose total profiles, total successful
  runs and the latest successful receipt date and jobs-found count without exposing another user.
- **FR-075**: An analyzed provider observation MUST be saved only while its captured catalog
  identifier, content revision and content fingerprint still match the canonical listing. A newer
  or missing observation MUST cause a nonfatal, bounded and observable skip without rewriting the
  catalog or persisting stale analysis; the newer revision MUST remain eligible for its own analysis.
  The same revision binding MUST apply across asynchronous local-model normalization: stale success
  or failure output MUST neither overwrite normalized fields nor change normalization status.
- **FR-076**: Career Vault search snapshots MUST redact bounded local and international telephone
  candidates embedded in otherwise eligible prose, including common whitespace, parenthesis, dot,
  slash and hyphen formats. Redaction MUST retain explicit guards for common years, date/time values,
  grouped counts and contextual metrics.
- **FR-077**: Complete vault erasure MUST derive user-referenced shared listings from both Job and
  Application logical-opportunity links. It MUST delete a listing only when no Job or Application
  owned by another user still references it.
- **FR-078**: Each owned Application MAY have one mutable working dossier draft in the local SQLite
  vault. Draft schemas MUST reject unknown fields, bound every list, string, evidence reference and
  aggregate payload, permit incomplete rows for autosave, and require a nonblank stable client id
  that is unique within each row collection. Browser storage MUST NOT hold the draft.
- **FR-079**: Draft create, update and delete operations MUST be authenticated, user-scoped and
  compare-and-swap revisioned. Saves MUST bind to the exact current Application revision and owned
  linked Resume Version. A stale application, resume or draft MUST fail without changing the saved
  row or visible form. Workspace publication MUST first save the current form, verify the exact
  draft projection, and remove that draft only in the transaction that records the immutable
  dossier event. The no-draft publication path MAY remain available to existing API clients.
- **FR-080**: Portable archive format v6 MUST include working dossier drafts. Inspection and restore
  MUST reject missing required fields, invalid revisions, malformed content, duplicate per-
  application rows and broken relationships before writes. Formats v1 through v5 MUST remain
  inspectable and restorable with an empty draft table. Application deletion and complete vault
  erasure MUST remove the associated draft through a database-enforced cascade.
- **FR-081**: First-use guidance MUST offer an existing-CV path and a manual-entry path without
  implying completion. When no Career Profile exists, an explicit source import MUST first persist
  the current minimum profile through the normal revisioned write, then upload the document through
  the existing bounded local source endpoint. A failed profile write MUST start no upload; a failed
  upload MAY leave the truthful empty profile in place but MUST preserve the selected file for retry.
  Accepted candidates MUST remain `imported` until the user reviews and explicitly confirms them.
- **FR-082**: The authenticated local API MUST expose only owned automation-grant metadata plus
  explicit create and revoke operations. Create and revoke MUST re-verify the current account
  password before lockout, enforce bounded labels, lifetimes, fixed operational scopes and active-grant
  count, and set `Cache-Control: no-store`. Repeated password failures MUST be bounded per account.
  They MAY temporarily pause issuance. While locked, a revoke request MUST NOT inspect its password
  or mutate the failed-check state; the authenticated desktop session MAY only revoke an owned
  grant. Listing MUST return every active owned grant plus bounded recent history. Creation MAY
  return the bearer only in that successful response; listing and revocation MUST never return or
  reconstruct it. Inactive history MUST be ordered by the transition that removed authority, and a
  successful create or first revocation MUST prune only that owner's inactive tail to the 100 most
  recent rows without touching active grants or another account. A repeated revocation MUST return
  the same metadata while its row remains inside that explicit retention window.
- **FR-083**: Agent Access MUST explain the desktop-vault lease and external-client disclosure,
  present fixed read, write and execution scopes in plain language, identify active, expired and
  revoked grants, and make
  one-time token copying and dismissal keyboard accessible. The renderer MUST keep a returned
  bearer only in transient component state, clear it on dismissal, sign-out and unmount, never
  write it to browser storage, and never copy it without an explicit user action. Setup copy MUST
  state truthfully that the `careeros` command is source-installed. One-time token appearance MUST
  be announced without reading the bearer, receive programmatic focus and restore focus to the
  issuance control after dismissal. Ordinary navigation and sign-out MUST wait for unresolved
  issuance. If a successful result arrives after forced unmount, the client MUST attempt to revoke
  that grant without displaying or storing its bearer. Forced sign-out MUST wait for this
  compensating cleanup before invalidating the authenticated server session. Clipboard failure
  MUST focus and select a keyboard-accessible read-only token field. The page MUST explain that an
  abrupt process or operating-system termination can outlive browser cleanup and direct the user to
  reopen the register and revoke any completed grant whose bearer was not saved. Real-browser
  acceptance MUST cover EN/IT, WCAG 2.2 AA, keyboard focus, 320/390/1440-pixel overflow, bounded
  error recovery and bearer absence after route exit.
- **FR-084**: At mobile widths, the workspace navigation drawer MUST be a labelled modal surface
  while open. It MUST make the skip link and workspace content inert and hidden from assistive
  technology, lock body scrolling, contain focus across its current controls, close on Escape,
  route activation or transition to the desktop layout, and restore the prior focus and scroll
  state when that target remains available. The visual scrim MAY close the drawer by pointer but
  MUST NOT create a keyboard target that competes with the labelled close control. Drawer and
  scrim transitions MUST respect `prefers-reduced-motion`. A closed off-canvas drawer MUST be
  hidden from keyboard and assistive-technology traversal at mobile widths.
- **FR-085**: The production renderer MUST emit English and Italian as independently loadable,
  locally bundled catalogues and load only the selected catalogue at login. A language change MUST
  disable both switch controls while its catalogue is pending, preserve the current language after
  a load failure and persist only a successfully loaded choice. The controls MUST retain visible
  keyboard focus, at least 44 by 44 CSS-pixel targets and WCAG AA small-text contrast. Production
  code MUST NOT import the eager bilingual catalogue used by tests. If initial selected-language
  loading and the English fallback both fail, the provider MUST expose static localized failure
  copy and a focused user-activated retry without automatic reload or repeated requests.
- **FR-086**: The production build MUST replace the complete Bootstrap Icons webfont with a
  deterministic MIT-attributed SVG-mask subset generated from every explicit `bi-*` production
  source token, plus a separate subset generated from lifecycle-only sources for initial UI. The
  build MUST reject computed, missing or stale icon names, emit no Bootstrap Icons WOFF/WOFF2
  asset, cap the initial JavaScript entry at 350,000 raw and 112,000 gzip bytes, cap one selected
  locale at 82,000 raw and 26,000 gzip bytes, cap lifecycle CSS at 23,000 raw and 6,200 gzip bytes,
  and cap worst-case login HTML, entry, one locale and CSS at 440,000 raw and 140,000 gzip bytes.
  Bootstrap and authenticated workspace code MUST load only after a session is established; their
  CSS and shell chunks MUST remain below 445,000/73,500 and 32,000/9,600 raw/gzip bytes
  respectively.
  The browser meta CSP MUST omit `frame-ancestors`, which is not enforced from meta; Nginx web
  distribution MUST retain `frame-ancestors 'none'` and `X-Frame-Options: DENY` response headers,
  while the native shell retains its Tauri CSP.
- **FR-087**: Every Dependabot ecosystem entry MUST apply a seven-day default cooldown to routine
  dependency updates. Release shell commands MUST consume repository, tag and commit context
  through quoted environment variables rather than directly interpolating GitHub expressions.
  The Nginx API proxy MUST normalize its upstream `Host` to `localhost` instead of forwarding the
  client-supplied host; existing loopback binding, TrustedHost and same-origin controls remain.
- **FR-088**: Runtime security configuration MUST accept only the canonical `development`, `test`
  and `production` environments, the exact `/api/v1` private prefix and the reviewed `HS256` JWT
  algorithm. Trusted hosts MUST be non-empty, unique canonical DNS or IP hosts with no wildcard,
  scheme, path, port or ambiguous authority; bracketed IPv6 configuration and request authorities
  MUST normalize to the same address. Production signing
  secrets MUST contain at least 32 non-control characters without surrounding whitespace.
  Credentialed CORS origins MUST be unique exact HTTP(S) origins or the supported Tauri origin,
  with no wildcard, credentials, non-root path, query or fragment. Renderer API bases MUST use the
  exact `/api/v1` path and, when absolute, an HTTP(S) loopback origin without credentials, query or
  fragment. Production CORS MUST require HTTPS except for exact loopback and supported local Tauri
  origins. Registration and login MUST reject, never truncate or hash, passwords over bcrypt's
  72-byte UTF-8 boundary. Authenticated API responses MUST be non-cacheable and dynamically
  uncompressed; Nginx MAY gzip public fingerprinted assets, MUST cache only those assets as
  immutable, and MUST make the SPA shell and unhashed assets revalidate. Explicit logout failure
  MUST unmount the private workspace, report the uncleared server session and offer a retry.
  Refresh cookies MUST use the narrow auth path and every issuance or clear operation MUST remove
  historical root-path canonical and legacy cookie variants. When `Origin` is absent, an auth
  mutation carrying browser `Sec-Fetch-Site` metadata MUST accept only one canonical
  `same-origin` value; `same-site`, `cross-site`, `none` or ambiguous values MUST fail closed.
  Native and CLI callers that omit both headers MUST remain supported. The repository MUST pin
  Node.js to `>=24.18.0 <25`, enable strict engine installation and run the same fail-fast check
  before every Node-, Vite-, Playwright- or Tauri-backed npm entry point.
- **FR-089**: Access and refresh JWTs MUST both include required `exp`, `iat`, `jti`, `sid`, `sub`
  and `type` claims and MUST share one stable `sid` for their persisted `AuthSession`. Every
  protected request MUST authorize the access token only after one indexed lookup binds its
  signed subject and `sid` to a live, unexpired, non-revoked row. A refresh MUST additionally match
  the SHA-256 digest of its presented JTI and atomically replace that digest while preserving the
  family id. Reuse of an older token, including the loser of a concurrent refresh, MUST revoke the
  family so both the winner's refresh and access credentials lose authority for new requests.
  Logout MUST atomically revoke every distinct valid family identified by the presented refresh
  cookie and access bearer, including an already rotated signed token. A failed logout commit MUST
  roll back every revocation, return `503`, clear every refresh-cookie variant to prevent automatic
  resurrection and leave only an in-memory access bearer available for explicit retry. At most
  eight session rows MAY exist per account, enforced by database-unique slots; allocation races
  MUST retry without exceeding that cap. Raw JWTs, raw JTIs and access-JTI state MUST NOT be
  stored. Pre-migration access and refresh tokens without `sid` MUST fail closed; invalid refresh
  cookies MUST be cleared. Portable export MUST exclude session rows; successful restore MUST
  revoke only the restored account's sessions and complete erasure MUST remove only that account's
  sessions. A failed issue, rotation or revocation commit MUST roll back. Once a revoke or delete
  commits, all later protected requests for that family MUST return `401`; a request already
  authorized before the commit MAY complete.
- **FR-090**: Every account MUST persist exactly one vault lifecycle state from `ready`,
  `reset_pending`, `restore_pending` and `erasure_pending`, with database checks that require a
  lowercase SHA-256 archive fingerprint only for restore recovery. A destructive transition MUST
  commit before mutation begins. A migration downgrade MUST refuse while any account is pending,
  and ordinary login, access refresh, automation authorization and agent-grant issuance MUST fail
  closed unless the state is `ready`.
- **FR-091**: Correct-password login for a pending account MUST return a non-refreshable access
  token whose signed purpose is `vault_maintenance` plus the durable `session_state`. That token
  MUST authorize only the matching reset, restore or erasure operation and MUST be rejected by
  normal workspace dependencies. Logout MUST invalidate a presented erasure-recovery sentinel;
  the old bearer MUST remain invalid after password reauthentication creates a replacement.
- **FR-092**: Reset, restore and erasure MUST share one process-wide maintenance mutex and an
  explicit reader/writer activity gate. New readers MUST fail fast once a writer is waiting,
  destructive work MUST run through one application worker, and cancellation MUST release every
  gate. `/health/live` MUST remain pure asynchronous process liveness. `/health/ready` MUST try the
  activity gate without blocking and report not-ready during writer contention or an unhealthy
  joined managed-runtime worker.
- **FR-093**: Reset and complete erasure MUST revoke every ordinary auth family before mutation and
  perform a final locked sweep before completion so a login racing the initial snapshot cannot
  survive. Reset MUST preserve only the currently presented maintenance authority; complete
  erasure MUST remove all account sessions. Erasure MAY supersede reset or restore recovery and
  MUST remove both published journal-owned bytes and owner-scoped staging.
- **FR-094**: Restore MUST durably journal every absent destination before the first publication.
  The per-account journal MUST have checksummed redundant copies, monotonic generations, a verified
  archive fingerprint, canonical managed paths and owner-scoped staging. Restart recovery MUST
  accept only the same verified archive; inconsistent copies or a different archive MUST fail
  closed. A successful retry or cleanup MUST remove the complete journal namespace durably.
- **FR-095**: Restore inspection and decoding MUST reject non-canonical UUID primary keys,
  control-character aliases, path-like identifiers, non-canonical storage bindings and any path
  outside the exact content-addressed asset, profile-photo or resume-artifact layout. Restore MUST
  preserve a journaled file if another account now references it, revoke restored sessions and
  automation grants, and restore every schedule disabled until the user explicitly enables it.
- **FR-096**: A failed restore MAY return the account to `ready` only after rolling back database
  work, durably deleting every still-exclusive journal-owned file, clearing recovery metadata and
  sanitizing recoverable SQLite/WAL bytes. Any incomplete cleanup MUST retain `restore_pending`
  with an actionable same-archive-retry-or-erasure response. Atomic publication MUST fsync content
  and parent metadata and use a write-through replacement primitive on Windows. Startup cleanup
  MUST delete only recognized `.write-*` temporaries under managed `assets` and `resumes` roots.
- **FR-097**: Portable archive verification MUST enforce at most 128 MiB compressed bytes,
  256 MiB uncompressed bytes, 5,000 members and 100,000 decoded records before unbounded work.
  Uploaded source reads MUST stop after the configured file limit plus one byte. Parsing failures
  MUST return stable content-free errors while private diagnostics remain sanitized.
- **FR-098**: Data-derived job and application links MUST open only absolute credential-free HTTPS
  URLs, while email actions MUST use the separately validated `mailto` path. The native opener
  capability MUST expose only those same two schemes; HTTP loopback authority remains exclusive to
  the authenticated desktop API bootstrap. Provider requests MUST reject every URL outside their
  configured exact HTTPS origin before network activity, MUST NOT follow redirects and MUST NOT
  inherit ambient proxy variables.
- **FR-099**: GitHub Actions artifacts used only as ordinary CI evidence MUST expire after seven
  days. Supply-chain evidence, build-once inputs, native target candidates and assembled release
  inputs MUST expire after fourteen days, and every upload step MUST set retention explicitly.
- **FR-100**: Login, recovery, localization and native boot MUST load one consolidated critical
  stylesheet containing no authenticated-workspace layout, feature or Bootstrap rules and only the
  icons referenced by those lifecycle surfaces. The complete icon subset, legacy styles, CareerOS
  workspace design system and layered Bootstrap compatibility sheet MUST load only through the
  authenticated workspace boundary in their established cascade order. Production contracts MUST
  enforce raw and gzip ceilings independently for critical CSS, complete initial resources and the
  lazy workspace stylesheet, and MUST preserve print, forced-colors, reduced-motion and responsive
  viewport behavior on the surface that uses it.
- **FR-101**: The native HTTP boundary MUST reject a request body above a configured hard ceiling
  while ASGI is receiving it, before multipart parsing and even when `Content-Length` is absent.
  Invalid, duplicate or conflicting declared lengths and mixed Content-Length/Transfer-Encoding
  framing MUST fail closed and close the connection. The default ceiling MUST leave bounded
  multipart framing room above the file ceiling and the reverse proxy MUST enforce the same limit
  with the API's content-free JSON and private-header failure contract.
  Every upload, decoded-text, page, archive-member, expanded-byte, resume-page and photo-pixel
  setting MUST have a positive startup-validated hard maximum. PDF and DOCX imports MUST enforce
  page, extracted-character, member and actual expanded-byte limits before persistence. CPU-heavy
  source parsing and image normalization MUST run outside the event loop so pure liveness remains
  responsive, and concurrent image requests MUST NOT mutate a process-global decoder limit.
- **FR-102**: Every local-inference and job-provider client MUST ignore ambient proxy settings,
  request identity encoding, reject compressed responses, refuse redirects and stop both declared
  and actually streamed bodies at a fixed ceiling before JSON parsing. Response envelopes, model
  catalogs, usage counters and provider page counts MUST be type- and range-validated; malformed or
  non-finite inference parameters, timeouts, context windows, output budgets, model identifiers,
  provider pagination, workload, coordinate and distance inputs MUST fail at construction or
  startup. Job-Room session/CSRF initialization MUST be single-flight and cancellation-safe, and a
  detail identifier MUST remain one percent-encoded path segment.
- **FR-103**: Managed runtime and model acquisition MUST use manually validated HTTPS redirects,
  allowlisted delivery hosts, bounded hop count, explicit connect/read/write/pool timeouts and no
  ambient proxy. Declared and actual archive size, member count, duplicate/case-colliding paths,
  special files, containment, checksum and cancellation MUST be checked before publication. A
  runtime installation MUST retain its checksum-pinned source archive and derive an inventory of
  every payload file; marker-only legacy installations MUST reinstall. Launch MUST reverify model
  size/hash and runtime inventory, minimize child environment and loader/proxy variables, use the
  runtime working directory and keep the process handle when termination is unconfirmed. Startup,
  installation, extraction and shutdown cancellation MUST converge within bounded retry/timeout
  policy without orphaning a managed process.
- **FR-104**: Content-addressed publication MUST be create-if-absent and MUST never replace a race
  winner. A losing identical writer MUST verify the durable bytes and report non-ownership; a
  conflicting writer MUST fail. SQLite source and normalized-photo persistence MUST serialize the
  shared file and unique row in one immediate transaction, remove only a file created by the
  failing transaction while its lock is held, and preserve cross-profile references during
  deletion. Successful responses MUST be prepared before commit so post-commit refresh failure
  cannot turn committed bytes into destructive cleanup. Equivalent concurrent imports across two
  real SQLite connections MUST converge to one file, one row per profile and no temporary residue.
  Resume publication MUST serialize version allocation, durably journal prospective PDF/DOCX paths
  before publication and reconcile ambiguous commit or process loss without deleting committed or
  shared bytes. Draft deletion and complete vault erasure MUST be idempotently retryable and remove
  every attributable publication journal and orphan while preserving foreign profile claims.
- **FR-105**: Each user MUST be able to create, inspect, update, enable, disable and delete bounded
  declarative job-provider configurations without changing application code. A configuration MUST
  have a stable identifier, unique user-owned key, revision, display metadata, adapter kind,
  request policy, response extraction mapping, enabled consent state and lifecycle timestamps.
- **FR-106**: Declarative provider requests MUST accept only HTTPS public destinations, validated
  same-origin paths, bounded GET or POST parameters, allowlisted template variables, bounded static
  headers, explicit timeouts, throttling, page size and page count. They MUST ignore ambient proxy
  settings, request identity encoding, refuse redirects and compressed responses, and reject
  loopback, link-local, private, credential-bearing or DNS-resolved private destinations before
  every request.
- **FR-107**: Declarative provider responses MUST be size-bounded before parsing and support strict
  JSON path extraction or a documented limited HTML selector subset. Field mappings MUST produce
  the canonical job contract, reject executable expressions and invalid selectors, normalize only
  bounded text and URLs, and report per-field diagnostics without persisting partial malformed
  observations.
- **FR-108**: Provider configuration validation MUST be available independently of network access.
  A separate explicit test action MAY perform one bounded request and return a small redacted sample
  and diagnostics. Provider list, export, logs and MCP results MUST redact secret-looking header
  values; updates MAY use a preserve-secret sentinel without returning the stored value.
- **FR-109**: Search orchestration MUST build its network-provider registry for the authenticated
  user on each run exclusively from enabled owned provider installations. A fresh vault MUST have
  no network providers; dormant application adapters and discoverable packs MUST NOT enter search.
  Imported native and declarative providers MUST share cancellation, resource, deduplication,
  observation, analysis and durable search-receipt behavior; one failed source MUST not make a
  successful local source disappear.
- **FR-110**: MCP MUST expose scope-filtered typed operations to read and save the Career Vault,
  list and maintain jobs, configure providers, run searches, inspect verified analysis, generate
  and publish resumes, create and revise application dossiers, manage tasks and append application
  stage events including `applied`. Tool visibility is advisory; every facade method MUST recheck
  its required scope and user ownership.
- **FR-111**: Agent mutations MUST use explicit identifiers, bounded idempotency keys where creates
  can be retried and expected revisions where an entity is mutable. A stale revision MUST fail with
  a stable conflict and MUST NOT silently merge, overwrite or retry against newer user data.
- **FR-112**: Agent-triggered analysis and search MUST require the same ready validated local model
  as desktop analysis and MUST fail closed without heuristic substitution. Provider network access
  MUST occur only for enabled sources and an authorized execution operation; deterministic local
  preparation and owned-record editing remain available without inference.
- **FR-113**: CareerOS MUST accept strict versioned JSON documents for one provider and for bounded
  provider packs. Pack parsing MUST forbid unknown fields, executable content and credential-bearing
  headers, cap document bytes and provider count, validate every entry before writes and commit all
  entries atomically or none. Duplicate document keys or conflicts with owned keys MUST fail.
- **FR-114**: A provider-pack native entry MUST reference only an application-shipped allowlisted
  adapter identifier. Importing such an entry activates no dynamic module loading and creates the
  same user-owned revision, enablement, portability and erasure boundary as a declarative provider.
- **FR-115**: The Swiss providers previously constructed at startup MUST be represented by an
  external bundled pack manifest containing Job-Room, SwissDevJobs and Adecco metadata. The same
  manifest MAY include reviewed data-only canton or specialist declarations. Pack listing MAY
  advertise the manifest, but installation and network consent require an explicit user or
  `providers:write` agent mutation.
- **FR-116**: UI, REST and MCP MUST support listing bundled packs, importing a bundled pack or supplied
  provider document, and revision-checked enable/disable and deletion. A newly imported provider is
  disabled by default; `activate=true` is an explicit network-consent mutation and MUST be visible in
  the result.

### Key Entities

- **Career Vault**: The complete locally owned data set, attachments, generated artifacts,
  settings, schema version, backup manifest and integrity metadata.
- **Career Profile**: The person's identity and preferences plus the structured collection of
  roles, achievements, skills, projects, education, credentials, languages and activities.
- **Career Fact**: An atomic, attributable statement with provenance, confidence,
  verification state, dates, visibility and relationships.
- **Evidence Source**: A local document, user assertion or imported record supporting one or
  more career facts, including integrity and extraction metadata.
- **Career Goal**: A desired career outcome with targets, constraints, deadlines, milestones,
  actions, skill gaps, progress and linked opportunities.
- **Opportunity**: A normalized role with source, organization, requirements, location,
  compensation, state, relevance evidence and user decisions.
- **Application**: The user's lifecycle for an opportunity, including stages, tasks, events,
  contacts, notes and related document versions.
- **Application Readiness Report**: A derived, versioned preflight record containing inspectable
  checks, weighted score, status, source revisions and a canonical content fingerprint.
- **Application Dossier Draft**: One private mutable working copy bound to an Application revision
  and Resume Version, with stable row identities and its own compare-and-swap revision.
- **Resume Document**: A user-owned resume with target, template category, evidence map,
  canvas state and a history of immutable versions.
- **Resume Version**: A snapshot of content, layout, provenance, validation results, exports
  and creation reason that can be compared or restored.
- **Local Model Profile**: A local model's identity, source, license, integrity, capabilities,
  hardware guidance, status and evaluation history.
- **AI Run**: A local task execution with input references, contract version, validation,
  evidence coverage, confidence, timing and failure classification.
- **Evaluation Suite**: A versioned set of synthetic or licensed cases, expected outcomes,
  metrics and reproducible run results.
- **Automation Grant**: A revocable, expiring authorization bound to one local user, represented
  at rest by a bearer-token digest, label, fixed scope set and lifecycle timestamps.
- **Job Provider Configuration**: A revisioned user-owned provider installation: either a
  declarative HTTPS request and JSON/HTML extraction contract or an allowlisted dormant native
  adapter reference imported from a provider document/pack, always with explicit enablement.
- **Provider Import Document**: A bounded, versioned, non-executable JSON envelope for one provider.
- **Provider Pack**: A bounded, versioned, non-executable JSON collection whose entries validate and
  import atomically; bundled discovery alone creates no provider and grants no network consent.
- **Auth Session**: One bounded browser refresh family identified by a non-secret `sid`, account
  id, unique slot, current JTI digest, expiry and optional revocation timestamp; no raw token or JTI
  is persisted or exported.
- **Vault Lifecycle**: The durable account state that distinguishes normal workspace authority
  from interrupted reset, restore or complete erasure, with an archive fingerprint only while a
  particular restore is recoverable.
- **Restore Ownership Journal**: A redundant checksummed per-account manifest of managed paths
  that were absent before restore, its monotonic generation and archive fingerprint, together with
  an owner-scoped staging directory used for restart-safe publication and cleanup.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a clean supported computer, at least 95% of first-time testers install and
  open the application within five minutes, excluding the separate local-model download time.
- **SC-002**: Automated privacy tests observe zero remote-AI requests and zero hidden outbound
  requests across launch, editing, inference, rendering, export and offline test workflows.
- **SC-003**: After a model is installed, 100% of core profile, goal, resume and AI workflows
  complete with networking disabled.
- **SC-004**: Across the offline golden set, at least 99% of accepted AI results satisfy their
  structured contract, 100% of generated claims have valid evidence references, unsupported
  accepted claims are 0%, and task-specific accuracy is at least 90% on the minimum model profile.
- **SC-005**: At least 90% of representative users can complete a detailed profile, set a goal,
  generate a resume, adjust it on the canvas and export it without assistance.
- **SC-006**: ATS exports achieve 100% extraction of required headings and body text in intended
  reading order across the release test corpus, with no photo or hidden text.
- **SC-007**: Every supported update and interrupted-migration test preserves or automatically
  restores the prior vault with zero lost committed records.
- **SC-008**: A backup restored to a fresh installation reproduces 100% of expected entities,
  relationships and attachment hashes in the portability test corpus.
- **SC-009**: Normal application exit leaves zero orphaned application-owned processes in 100%
  of lifecycle tests; normal-exit tests observe an authenticated graceful request before any
  forced fallback, watchdog tests prove cleanup is awaited before hard exit, and crash-containment
  tests preserve a finite shell-exit bound. Crash recovery restores a usable workspace in under
  30 seconds in 95% of supported test environments.
- **SC-010**: Every published artifact passes install, launch, offline reopen, export and
  uninstall smoke tests and is accompanied by a checksum and software inventory.
- **SC-011**: Core keyboard-only workflow tests complete without a trap and all actionable
  controls expose a visible focus state and accessible name.
- **SC-012**: Automated UI tests confirm English on a clean first launch, an immediate
  English/Italian switch, local persistence of that choice and English demo-recording selectors.
- **SC-013**: Adversarial release tests reject unsafe names, case-insensitive collisions, missing
  or extra targets, altered checksums, unsigned/off-branch tags, paginated duplicate drafts,
  foreign contracts and mismatched remote assets; deterministic retry tests prove no duplicate
  mutation after every create, upload and publish ambiguity.
- **SC-014**: Backend and UI acceptance tests prove that an unchanged application readiness report
  produces identical canonical JSON and Markdown bytes, accurate blocker counts and a matching
  SHA-256 response header with all networking disabled.
- **SC-015**: Artifact acceptance tests prove deleted, corrupt, path-escaping, size-mismatched and
  unreadable resume files cannot pass readiness; keyboard tests prove focus containment, Escape,
  background inertness/scroll lock and opener-focus restoration for the application dialog.
- **SC-016**: Concurrency, cross-user, planner-boundary, replay-integrity, projection-read and
  repeatable-dossier tests pass with networking disabled and demonstrate exactly one CAS winner,
  zero manual cross-user collisions and no silently omitted UI rows.
- **SC-017**: Contract tests prove that 100% of opportunity-analysis persistence paths require a
  ready loopback model and validated structured output, model failures produce zero heuristic
  analysis rows, and the authenticated onboarding gate unlocks only after the content-free
  structured readiness probe succeeds.
- **SC-018**: Agenda acceptance tests classify fixed deadlines and DST-correct day boundaries exactly, return zero
  foreign-user fields, perform no event-payload replay, produce counts and rows in one SQL
  statement, disclose every horizon/limit omission, refresh at temporal/visibility boundaries,
  preserve a usable application board when the agenda request fails, and pass Chromium geometry
  and contrast checks at 320 px.
- **SC-019**: Inspection acceptance tests prove that valid historical and current archives return
  stable content-free summaries; malformed, oversized, traversing, duplicate, tampered,
  relationship-invalid and projection-inconsistent archives fail without changing database rows,
  application files or the active session; and inspection remains available with a populated vault.
- **SC-020**: Desktop save fault tests prove that a digest mismatch or write/rename/read failure
  never replaces the previous destination with unverified bytes, removes managed temporary files,
  and surfaces a verified result only when the final destination digest matches exactly. Frontend
  tests prove distinct verify and restore controls, English/Italian copy and keyboard-accessible
  summaries.
- **SC-021**: Automation acceptance tests prove typed read and mutation tool discovery and
  invocation through an official in-memory and real stdio MCP client, exact scope filtering,
  cross-user isolation, revision conflicts, token digest storage, expiry and revocation, bounded
  outputs, stdout protocol purity, explicit disclosure acknowledgement and exclusive-lease failure
  while the desktop is active.
- **SC-022**: Listing-observation acceptance tests prove that unchanged repeats advance only
  last-seen time; changed repeats advance one revision and require fresh verified analysis; and
  refreshes preserve profile decisions, application state and immutable application snapshots.
  Migration tests prove a non-null conservative backfill, while missing, failed and partial source
  results never produce an inferred closure.
- **SC-023**: Search-receipt acceptance tests prove exactly one count increment for an idempotently
  repeated `done` update, monotonic increments across later successful retries, no receipt mutation
  after error/cancellation, survival after polling-state pruning beyond 24 hours, user isolation,
  fixed JSON bounds with no private search content, conservative migration and portable round-trip.
- **SC-024**: Profile-overview acceptance tests cover more than 100 owned profiles, deterministic
  pagination, whole-vault receipt aggregation, cross-user isolation and the absence of CV, cache and
  normalized fields. Catalog race tests prove A→B→save(A) skips without rewriting, A→A saves,
  missing catalog rows skip, and the same current revision can be saved for two owned profiles.
  A deterministic model-await interleaving proves normalization output for A cannot mutate B.
- **SC-025**: Dossier-draft acceptance tests prove durable reload, bounded and uniquely keyed rows,
  cross-user isolation, one compare-and-swap winner, explicit rebase after Application or Resume
  changes, form preservation after save/publication failure, exact atomic publication, v6 portable
  round-trip, adversarial preflight rejection, v1-v5 compatibility and migration downgrade/upgrade.
- **SC-026**: First-use UI tests prove that a new account can select a supported CV before a profile
  exists, that the profile write completes before the source upload starts, that write failure
  starts no upload, that upload failure keeps the file selectable for retry, and that accepted
  candidates remain unconfirmed with a keyboard-operable route to review them. Existing profiles
  import without an unnecessary profile write, and the complete path makes no model call.
- **SC-027**: Agent Access acceptance tests prove password re-authentication, cross-user grant
  isolation, exact scope/lifetime bounds, no-store issuance, one-time bearer output, metadata-only
  listing, idempotent revocation and stable content-free errors. Frontend tests prove explicit-only
  clipboard use, bearer cleanup on dismissal and unmount, keyboard operation, honest source-install
  guidance and usable grant listing after mutation failures.
- **SC-028**: Workspace-shell tests prove modal semantics, inert and assistive-technology-hidden
  background content, body-scroll restoration, forward and reverse focus wrapping, Escape and
  opener-focus restoration, route and desktop-resize closure, unmount cleanup and a non-focusable
  scrim. Real Chromium checks 320, 375, 991 and 1,280 px geometry plus reduced-motion transition
  suppression without horizontal overflow.
- **SC-029**: The production build reports and enforces entry, selected-locale, CSS and worst-case
  login raw/gzip budgets, emits two independently loadable catalogues and zero icon-font files.
  Real Chromium at 390 px proves English and persisted Italian each load only their selected
  catalogue, English-to-Italian switching succeeds offline, both states have zero WCAG A/AA/2.1-AA
  axe violations, inactive-language and privacy-copy contrast are at least 4.5:1, both language
  targets are at least 44 by 44 CSS pixels, keyboard focus is visible, disabled submit semantics
  remain correct, subset icons have visible geometry and no CSP warning or page error occurs.
  A forced dual-catalogue failure proves localized recovery, focused retry and exactly one new
  selected/fallback attempt only after each explicit activation.
- **SC-030**: Configuration contract tests prove all five Dependabot entries use a seven-day
  default cooldown, release command arguments contain no direct `github.repository`,
  `github.ref_name` or `github.sha` interpolation, and the API proxy sends exactly
  `Host: localhost` without reflecting `$host`.
- **SC-031**: Configuration, API and renderer tests reject malformed environment, algorithm,
  signing secret, CORS, API-base and overlong UTF-8 password inputs. A production container smoke
  proves exactly one private cache policy, no API compression for a response above 1,000 bytes,
  no-cache HTML/unhashed assets, immutable and gzip-compressed fingerprinted assets, and a
  failed-then-successful explicit logout keeps the workspace unmounted until the server cookie is
  cleared. Browser-origin tests reject every mutation carrying non-same-origin Fetch Metadata
  without `Origin`, while native callers omitting both remain valid. Production-build measurements
  remain within every login and authenticated-workspace raw/gzip ceiling. Runtime contract tests
  prove every Node-backed npm entry point accepts Node 24.18 and fails before work below the floor.
- **SC-032**: Auth-session acceptance tests prove required-claim rejection, digest-only storage,
  stable access/refresh family binding, live access rejection after logout, replay, restore and
  erasure, one compare-and-swap winner under a real two-connection refresh race, and rejection of
  that winner's access after the loser revokes the family. They also prove atomic two-family logout
  rollback, `503` plus cookie clearing and bearer retry after commit failure, last-started-wins
  frontend login/register/refresh behavior, rejection and cookie clearing for pre-migration
  tokens, an eight-row database-enforced per-account cap, cross-user restore/erasure isolation,
  migration cascade and downgrade/upgrade, and zero partial persistence after forced failures.
- **SC-033**: Vault-lifecycle acceptance tests kill restore after the first publication, prove a
  same-fingerprint retry converges, prove a different archive is rejected, and prove lost-archive
  erasure removes final bytes, owner staging and the journal. Injected late restore failures leave
  zero private marker bytes in SQLite, WAL and SHM; incomplete cleanup retains recoverable state.
- **SC-034**: Auth and race tests prove pending accounts cannot obtain normal access, refresh or
  automation authority; maintenance tokens fail on ordinary routes; reset's final sweep revokes a
  family created after its initial snapshot; logout invalidates an erasure sentinel; and only a
  new correct-password maintenance login can complete the operation.
- **SC-035**: Activity tests prove one writer excludes readers, queued writers prevent reader
  starvation, cancellation releases both the maintenance mutex and activity gate, liveness stays
  responsive during blocked database work, and readiness returns not-ready without waiting behind
  a writer or unhealthy joined managed-runtime worker.
- **SC-036**: Portability and storage tests reject traversal, control-character and non-canonical
  UUID identities plus asset, photo and resume binding aliases; preserve a published file after a
  different account binds it; validate restart journal corruption and monotonicity; clean only
  managed stale temporary files; and exercise atomic replacement of an existing destination on
  every supported platform, including the write-through Windows implementation.
- **SC-037**: Resource-bound tests reject archives above every compressed, uncompressed, member
  and record ceiling before mutation, prove uploads read only the limit plus one byte, and prove
  corrupt PDF/document diagnostics expose neither parser internals nor source content.
- **SC-038**: Renderer and native-capability tests reject HTTP loopback and credential-bearing
  external targets, provider transport tests reject scheme, host, port and redirect expansion
  before a second request, and workflow tests prove no artifact upload inherits GitHub's default
  retention.
- **SC-039**: A fresh production build emits exactly one initial lifecycle stylesheet at no more
  than 23,000 raw and 6,200 gzip bytes, keeps worst-case login resources below 440,000 raw and
  140,000 gzip bytes, and emits exactly one lazy authenticated-workspace stylesheet below 445,000
  raw and 73,500 gzip bytes. The validator proves workspace selectors and Bootstrap are absent from
  initial CSS while authentication, recovery, native boot, forced-colors, reduced-motion and mobile
  lifecycle rules remain present; the lazy sheet retains workspace selectors, print and all
  responsive/accessibility media contracts. Full frontend, distribution and real-browser login
  and workspace responsive gates pass without weakening the established cascade.
- **SC-040**: Request-boundary tests reject oversized declared and chunked bodies plus duplicate or
  mixed framing before route completion with private security/no-store headers, while exact-boundary
  bodies pass; the real Nginx image returns the same JSON 413 contract. Adversarial PDF,
  DOCX and image tests prove every configured decompression/page/pixel ceiling, and concurrent slow
  source/image parsing leaves `/health/live` responsive in under one second.
- **SC-041**: Provider and inference tests use real HTTPX streams to reject long, malformed,
  compressed, oversized and schema-invalid responses; construction tests reject non-finite or
  out-of-range controls. Cancellation and concurrent Job-Room bootstrap tests leave no partial
  client, redirect or cross-origin request.
- **SC-042**: Managed-runtime tests reject redirect expansion, archive aliases, special entries,
  declared/actual size divergence, inventory/model tampering, environment leakage and unconfirmed
  process termination. A real checksum-pinned Windows ARM64 release archive reproduces its complete
  inventory without downloading or launching the 1.83 GB model.
- **SC-043**: Repeated multi-thread and real two-connection SQLite tests prove exactly one atomic
  byte publisher, no replacement under conflicting content, one source/photo row per profile,
  serialized monotonic resume versions, crash-reconciled publication journals, retryable deletion,
  preserved shared ownership, bounded profile revision and zero `.write-*` residue.
- **SC-044**: Provider configuration contract and integration tests cover JSON and HTML adapters,
  create/update/disable/delete with revision conflicts, secret redaction and preservation, invalid
  mappings, retries and pagination ceilings. Real streamed HTTP tests reject HTTP, credentials,
  redirects, compression, oversized bodies and direct or DNS-resolved private destinations without
  emitting a second request or persisting a partial observation.
- **SC-045**: Search acceptance tests prove that a fresh Vault constructs no network adapter and
  that only explicitly imported/configured and enabled providers enter the same user-scoped
  pipeline. Disabled, absent or foreign installations perform zero network work; one source failure
  remains isolated, observations deduplicate durably and verified local-model analysis plus the
  successful-search receipt follow existing invariants.
- **SC-046**: End-to-end MCP tests use an operational grant to create and validate a provider, run
  a search, inspect a verified job, generate and publish a resume, create and publish an application
  dossier, append `applied` and add a follow-up task. Read-only and partial grants discover no
  unauthorized mutations; direct facade calls still fail, stale revisions never overwrite, all
  records remain owned and revoked tokens cannot continue the workflow.

## Assumptions

- The first production release is a single-user personal desktop application; shared vaults,
  organization administration and real-time collaboration are out of scope.
- Windows 10/11, current and previous major macOS releases, and maintained 64-bit desktop Linux
  distributions are the target support envelope; exact release matrices are decided in planning.
- Internet access is optional and used only after consent for model acquisition, update checks
  and enabled job sources. Offline installation packages may be added later.
- The default compact model is selected for common consumer hardware; larger optional profiles
  may improve quality but cannot weaken evidence and validation gates.
- Career guidance is decision support, not legal, immigration, financial or employment advice.
- Existing trustworthy local data is migrated into the new vault rather than discarded.
- Code signing and notarization are release requirements when publisher credentials are
  available; development artifacts must identify their unsigned status honestly.
- Raw imported source files remain local and can be excluded independently from portable backups.
- The CLI/MCP interface is installed from a source checkout with the reviewed dependency lock;
  native desktop installers do not add it to the operating system's command path.
- CareerOS controls data only until it writes an MCP result to the connected client's stdio
  channel. The client and its provider remain separate trust boundaries.
