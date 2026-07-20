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

1. **Given** no local model, **When** an AI-assisted action is requested, **Then** the
   application explains what is missing and offers an explicit local model setup path while
   preserving deterministic non-AI functionality.
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
  installed or an AI task is unavailable.
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

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a clean supported computer, at least 95% of first-time testers install and
  open the application within five minutes, excluding optional model download time.
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
