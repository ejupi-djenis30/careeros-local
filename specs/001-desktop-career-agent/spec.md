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
3. **Given** the application is closed normally or after a crash, **When** process state is
   inspected, **Then** no application-owned background service remains orphaned.
4. **Given** an application update, **When** it is installed, **Then** the vault is migrated
   safely and existing profile, job, application, goal and resume data remain available.

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

### User Story 10 - Read CareerOS safely from a coding agent (Priority: P2)

A person can let Codex, Claude Code or a shell script inspect a limited part of one CareerOS
account without exposing the whole vault or creating a second writer. The person chooses the
scope and lifetime, receives one revocable bearer token, and must acknowledge that the connected
agent may pass returned metadata to its own provider.

**Why this priority**: Application follow-up and career planning often happen while working in a
terminal. A dedicated read boundary is safer and more predictable than giving an agent the vault
file, a desktop session token, arbitrary filesystem access or a generic database command.

**Independent Test**: Create two local users and grants with different scope sets. Connect through
the official MCP client over a real stdio subprocess, list and call the visible tools, and verify
scope enforcement, user isolation, bounded typed results, stdout protocol purity, token redaction,
revocation and expiry. Keep the desktop process open for a second run and verify that automation
fails with `vault_busy` instead of opening another connection.

**Acceptance Scenarios**:

1. **Given** an existing local account and a closed desktop app, **When** the user runs
   `careeros authorize`, authenticates interactively and selects a lifetime and at least one
   explicit scope, **Then**
   CareerOS returns a random bearer token once and persists only its SHA-256 digest, account
   binding, label, scopes, expiry and revocation state.
2. **Given** a grant with only `applications:read`, **When** an MCP session starts, **Then** only
   the three application tools are registered and a direct attempt to use another facade read
   fails with `scope_denied`.
3. **Given** a valid grant, **When** the CLI or MCP tools inspect CareerOS, **Then** results are
   bounded typed projections and contain no resume body, source-document content, contact field,
   prompt, artifact byte, bearer token or local storage path.
4. **Given** CareerOS Local is already running, **When** a CLI command or MCP tool call tries to
   read the vault, **Then** it fails with `vault_busy`. **Given** an idle MCP server, **When** the
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

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The product MUST be installable and launchable as a desktop application on
  supported Windows, macOS and Linux systems without developer tooling.
- **FR-002**: The desktop application MUST own startup, health monitoring, restart limits and
  shutdown of every packaged service and local model process it starts.
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
- **FR-061**: A source-installed command MUST expose fixed CareerOS read operations to a human CLI
  and an MCP server over standard input/output. MCP MUST open no network listener, initiate no
  provider request and expose no generic prompt, SQL, filesystem, mutation, export, restore,
  erasure or job-search operation.
- **FR-062**: Automation authorization MUST require an interactive CareerOS password check and
  create a grant for exactly one local user with a bounded lifetime and an explicit subset of
  `system:read`, `career:read`, `resume:read` and `applications:read`. The bearer token MUST be
  returned once; only a cryptographic digest and non-secret grant metadata may be persisted.
- **FR-063**: Every CLI data read, MCP bootstrap and MCP tool call MUST hold the existing exclusive
  desktop vault lease for that operation. MCP MUST release the lease while idle, then reacquire it
  and revalidate the grant before every tool read. Ordinary reads MUST reject an outdated schema
  without migration; only explicit authorization may migrate while the desktop is closed.
- **FR-064**: MCP MUST register only the tools allowed by the authenticated grant. Every tool
  result MUST use a bounded typed contract and omit raw resumes, source documents, contact data,
  prompts, artifact bytes, tokens and local storage paths. Scope checks in the service MUST remain
  authoritative even if client-side tool annotations are ignored.
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
  password before lockout, enforce bounded labels, lifetimes, fixed read scopes and active-grant
  count, and set `Cache-Control: no-store`. Repeated password failures MUST be bounded per account.
  They MAY temporarily pause issuance. While locked, a revoke request MUST NOT inspect its password
  or mutate the failed-check state; the authenticated desktop session MAY only revoke an owned
  grant. Listing MUST return every active owned grant plus bounded recent history. Creation MAY
  return the bearer only in that successful response; listing and revocation MUST never return or
  reconstruct it.
- **FR-083**: Agent Access MUST explain the desktop-vault lease and external-client disclosure,
  present fixed scopes in plain language, identify active, expired and revoked grants, and make
  one-time token copying and dismissal keyboard accessible. The renderer MUST keep a returned
  bearer only in transient component state, clear it on dismissal, sign-out and unmount, never
  write it to browser storage, and never copy it without an explicit user action. Setup copy MUST
  state truthfully that the `careeros` command is source-installed. One-time token appearance MUST
  be announced without reading the bearer, receive programmatic focus and restore focus to the
  issuance control after dismissal. Ordinary navigation and sign-out MUST wait for unresolved
  issuance. If a successful result arrives after forced unmount, the client MUST attempt to revoke
  that grant without displaying or storing its bearer. Forced sign-out MUST wait for this
  compensating cleanup before invalidating the authenticated server session. Clipboard failure
  MUST focus and select a keyboard-accessible read-only token field.

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
  of lifecycle tests; crash recovery restores a usable workspace in under 30 seconds in 95%
  of supported test environments.
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
- **SC-021**: Automation acceptance tests prove typed read-only tool discovery and invocation
  through an official in-memory and real stdio MCP client, exact scope filtering, cross-user
  isolation, token digest storage, expiry and revocation, bounded outputs, stdout protocol purity,
  explicit disclosure acknowledgement and exclusive-lease failure while the desktop is active.
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
