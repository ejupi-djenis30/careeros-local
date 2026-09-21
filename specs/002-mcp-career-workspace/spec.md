# Feature Specification: MCP Career Workspace and Template Studio

**Feature Branch**: `codex/002-mcp-career-workspace`
**Created**: 2026-09-13
**Status**: Implemented; final validation and convergence complete
**Input**: Owner requests CareerOS analysis with Codex or Claude Code through MCP, suitable
opportunities and application material with multiple templates like the manual ../Career
workflow. Complete GitHub Spec Kit artifacts precede code. Implementation began through
Antigravity and GPT-5.3-Codex-Spark; after their quota exhaustion, the owner explicitly
authorized the coordinating Codex agent and its subagents to implement and correct the work
directly. Constitution 2.0.0 authorizes this scoped external-agent disclosure.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Work with my chosen agent while CareerOS stays open (Priority: P1)

I choose local intelligence or an external Codex/Claude Code client, understand what is shared,
authorize only required capabilities, and connect without closing my workspace. I create an
analysis request, see it waiting for my agent, review returned results and can revoke access.

**Why this priority**: The current read-only interface cannot perform the requested workflow.
**Independent Test**: Without a local model, a synthetic account authorizes one client, creates
a request, completes it through a real MCP session and reviews the returned result in the app.

**Acceptance Scenarios**:
1. **Given** local mode and no grant, **When** agent access opens, **Then** no data is shared;
   scope, expiry, external processing and setup for both clients are explained.
2. **Given** an acknowledged, password-confirmed grant, **When** its client connects while the
   desktop is open, **Then** it sees only owned, permitted work and context.
3. **Given** queued work without an agent response, **When** its status is viewed, **Then** it
   remains pending with a next action; no heuristic or local-model status labels it analyzed.
4. **Given** revocation, expiry or vault maintenance, **When** a client reads/submits again,
   **Then** it receives a content-free denial and no mutation occurs.
5. **Given** an existing read-only grant, **When** upgraded, **Then** detailed career text and
   proposed writes stay unavailable until a new grant explicitly includes those scopes.

### User Story 2 - Find and assess opportunities suited to me (Priority: P1)

I enter target roles, languages, location/commute, contract and availability preferences.
My agent brings real vacancies into CareerOS, checks hard requirements and uncertainty, ranks
suitable roles with evidence, and leaves me in control of saving them as applications.

**Why this priority**: Reproduces the useful research and matching in Career.
**Independent Test**: Import two synthetic listings and a duplicate through the agent, return
evidence-linked assessments and accept one into the existing job/application pipeline.

**Acceptance Scenarios**:
1. **Given** explicit search intent and confirmed facts, **When** I request opportunities,
   **Then** the agent receives bounded contact-redacted evidence and explicit preferences.
2. **Given** an agent-found listing, **When** proposed, **Then** source URL, employer, title,
   location, source observation time and captured advert accompany it.
3. **Given** mandatory requirements, **When** matching returns, **Then** eligible/hold/reject
   gates include evidence, missing facts, uncertainty and explained score dimensions; unknown
   language, credential, availability or location requirements do not silently pass.
4. **Given** a duplicate listing or repeated acceptance, **When** retried, **Then** one owned
   opportunity/application is reused without duplicate confirmed records.
5. **Given** an updated profile or advert, **When** an old result arrives or is accepted,
   **Then** it is rejected as stale and I can issue a fresh request.
6. **Given** hostile instructions embedded in an advert, **When** context is delivered,
   **Then** the advert is labeled untrusted and cannot change server authority or approval.

### User Story 3 - Select and change reusable CV templates (Priority: P1)

I browse templates by professional family, language and layout, preview selected facts, edit
content and switch designs without losing approved wording.

**Why this priority**: Two hard-coded choices do not reproduce Career's template variety.
**Independent Test**: Create two CVs from a preset, edit one, change its layout, publish PDF/DOCX
and restore a prior version; verify the other CV and template remain unchanged.

**Acceptance Scenarios**:
1. **Given** the gallery, **When** filtering, **Then** software, cloud/platform, Swiss software,
   Swiss infrastructure, logistics, retail and operational families have declared EN/DE
   languages and ATS, Swiss photo or Swiss operational layouts.
2. **Given** approved content, **When** changing template, **Then** text, selected evidence and
   overrides survive; incompatible photo/layout settings are explained.
3. **Given** ATS, **When** exporting, **Then** the result is single-column, photo-free and
   text-selectable in reading order. Other layouts remain readable without color.
4. **Given** old published versions, **When** viewing/restoring/exporting, **Then** their bytes
   and immutable snapshots remain valid.
5. **Given** long content, diacritics, links, no photo or oversized images, **When** rendering,
   **Then** unsupported content or overflow is reported instead of dropping text.
6. **Given** an immutable preset ID/version, **When** a draft or generated CV supplies a different
   locale, **Then** the write is rejected before storage so every saved selection remains valid for
   preview, export and MCP material work.

### User Story 4 - Prepare a complete reviewable application packet (Priority: P1)

From one opportunity I ask my agent for a tailored CV, matching letter, email and answers.
CareerOS checks evidence, allows editing/approval and exports a locally generated packet with
selected documents and a manifest of their actual bytes.

**Why this priority**: Usable materials are the requested outcome beyond analysis.
**Independent Test**: Complete a fictional opportunity-to-packet journey without a local model,
review the returned draft, export and reopen each document, checking content and manifest.

**Acceptance Scenarios**:
1. **Given** a saved application and confirmed facts, **When** requesting materials, **Then**
   the request binds application, profile, advert, target CV and dossier draft revisions and
   selected template versions; later manual edits cannot be overwritten by late results.
2. **Given** returned material, **When** submitted, **Then** career claims cite supplied fact
   IDs, unsupported claims fail validation and valid output remains an unapproved proposal.
3. **Given** a valid proposal, **When** I accept it in CareerOS, **Then** CV/dossier drafts update
   atomically with provenance/revisions; no document is automatically published.
4. **Given** reviewed material, **When** exporting, **Then** the packet includes CV PDF/DOCX,
   letter PDF/DOCX when selected, email subject/body/attachment checklist, answers, advert
   snapshot and evidence/quality notes. Unselected optional items are accurately absent.
5. **Given** email drafting, **When** choosing short cover email or motivational email,
   **Then** only that mode is used and listed attachments match actual readable packet files.
6. **Given** unresolved placeholders, stale inputs, unsupported claims or missing attachments,
   **When** finalizing, **Then** blockers are explained. Preparation/export never marks sent;
   sending and confirmation of application status remain user actions.
7. **Given** two sessions of the same owner editing one dossier revision, **When** both save,
   **Then** exactly one succeeds and the other reports a revision conflict without losing the
   successful edit. A surrounding material acceptance transaction retains commit/rollback control.
8. **Given** a reviewed dossier bound to a specific CV draft revision, **When** publishing,
   **Then** the explicitly selected version represents that approved draft, readiness describes
   that selected CV, and every published letter/email/provenance field matches the saved draft.
9. **Given** a packet commit whose acknowledgement or later journal cleanup fails, **When**
   recovering, **Then** committed artifact bytes remain available, incomplete writes reconcile
   under the vault lock, and a schema 3 packet is never regenerated as a legacy packet.
10. **Given** a current accepted and attested MCP analysis, **When** creating an application from
    that opportunity, **Then** its exact match projection remains receipt-verified in the immutable
    application snapshot; stale, foreign or unattested analysis is still neutralized.

### User Story 5 - Bring my manual Career workflow into the vault (Priority: P2)

I select local source documents, preview candidate facts/preferences and confirm what to import.
My original files stay unchanged and templates do not become sources of confirmed facts.

**Why this priority**: Existing work must be reusable without embedding personal data in the app.
**Independent Test**: Import fictional Career-shaped profile/narrative/goal documents through
the supported file flow, review candidates and generate a packet using a matching preset.

**Acceptance Scenarios**:
1. **Given** selected source documents, **When** imported, **Then** originals stay unchanged,
   candidates are reviewable, narrative remains distinct from confirmed truth.
2. **Given** personal content/instructions in references, **When** adapted, **Then** only chosen
   confirmed content enters the vault; distributed presets have no real personal data.
3. **Given** unsafe or unsupported inputs, **When** importing, **Then** limits are reported;
   scripts, links, external assets and arbitrary paths are not executed or fetched.
4. **Given** selected goal candidates and existing preferences, **When** accepting them,
   **Then** the whole combined preference value is validated before mutation; conflicting scalar
   candidates require an explicit choice and failed acceptance preserves the selection and draft.
5. **Given** an upload or profile save in progress, **When** the user selects another source or
   accepts another preference, **Then** a late response cannot replace the newer selection or
   erase a later edit; the UI never reports unsaved changes as saved.
6. **Given** unsupported goal prose or invalid numeric syntax, **When** parsing,
   **Then** omissions receive bounded review notes, overflow has an explicit summary, and
   negative or fractional values are never silently converted into different valid integers.

### Edge Cases

- Concurrent agents: identical retry returns the same receipt; conflicting retry fails.
- Disconnected clients: durable cancellation/expiry rejects late results after restart.
- Grant revocation during work: replacement grants cannot inherit authority implicitly.
- Foreign IDs/evidence, unknown fields, invalid scores, oversized context/results, unsafe URLs,
  redirects, traversal and HTML/script payloads fail at the appropriate boundary.
- Reset/restore/erasure cancels live authority; portable records restore without active grants.
- Advert changes after generation: history remains visible but stale material cannot publish.
- Template switching survives duplication/restart/restore without modifying published bytes.
- Publication failure cleans staged files and rolls back metadata together.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Distinguish local and external workflows with truthful queued, returned, canceled,
  expired, accepted and rejected states; show failed-operation feedback separately without
  consuming pending work or claiming completion; no unsolicited fallback. [US1]
- **FR-002**: Provide usable token-free Codex/Claude connection instructions for the open
  desktop and preserve the existing offline read-only interface. [US1]
- **FR-003**: Require disclosure, password-confirmed grants, bounded expiry, separate detailed
  context and proposal scopes, and authority checks on every operation. Every interface that can
  issue these extended scopes must collect and propagate an explicit disclosure acknowledgement.
  [US1]
- **FR-004**: Expose only bounded owned context with confirmed fact IDs, explicit preferences
  and selected snapshots; redact contacts by default and state truncation. [US1,US2]
- **FR-005**: Persist requests/proposals with owner, grant/client provenance, input revisions
  and digest, timestamps, contract version and idempotency key. [US1,US2,US4]
- **FR-006**: Accept discovery from client research and existing manual import, with source,
  observation time and text; no invented vacancies or assumed open/closed status. [US2]
- **FR-007**: Explain hard gates and dimension scores with evidence/uncertainty; reject foreign
  or missing references and invalid scores before storing validated analysis. A current accepted
  external receipt remains trusted when projected into an application snapshot. [US2,US4]
- **FR-008**: Deduplicate retries and accepted opportunities by source identity using existing
  catalog/application services. [US2]
- **FR-009**: Check stale inputs at submission AND acceptance using atomic revision checks for
  profile, advert, application, CV and dossier draft targets. All accepted writes are one
  transaction, and edits create new revisions requiring revalidation at publication. [US2,US4]
- **FR-010**: Ship at least nine versioned family/language presets across seven families and
  three layouts: international software/cloud EN; Swiss software/infrastructure EN+DE;
  logistics/retail/operational DE. Separate layout, language and content. [US3]
- **FR-011**: Preserve selected facts, manual edits and immutable publications across template
  switching, duplication, migrations, restore and portability. [US3]
- **FR-012**: Preview/render locally without remote fonts/images/styles/code; support A4,
  PDF/DOCX, selectable text, normalized optional photo and explicit quality limits. [US3]
- **FR-013**: Accept proposed CV, cover letter, email and form answers under one evidence
  contract with manual review/editing and bound application/template versions. [US4]
- **FR-014**: Keep approval, fact confirmation, publication, transmission, grant management
  and destructive operations outside the MCP tools. [US1,US4]
- **FR-015**: Export reviewed packets with real digests, selected materials, source snapshot,
  evidence and quality; keep prepared versus sent states separate. [US4]
- **FR-016**: Import explicitly chosen references into reviewable candidates, extending existing
  import for supported Career text formats; preserve originals, exclude credentials/scripts. [US5]
- **FR-017**: Preserve local endpoint validation, archive bounds, manifest checks, atomic writes,
  account isolation, exclusive desktop vault lease and secret-free logging. Parse every trusted
  archive and packet JSON boundary with duplicate-key and non-finite-number rejection.
- **FR-018**: New UI actions are localized and keyboard accessible; errors preserve work and
  offer retry/review without claiming success.
- **FR-019**: Upgrade/downgrade/upgrade preserves old grants/documents; new persistent records
  participate in portability and destructive vault lifecycle.
- **FR-020**: Use fictional fixtures; behavior changes have domain, protocol, UI and failure
  tests with exact recorded evidence.
- **FR-021**: Installed desktop setup points to an available distributed bridge launcher,
  without an implicit checkout or global Python dependency. Developer and installed-client
  setup are labeled separately; installed connections survive an app restart without manually
  replacing an ephemeral port. Contract tests are not a claim of live-client smoke. [US1]
- **FR-022**: Template locale controls labels/style, not silent content translation. Preserve
  approved text and declare its language accurately; translation needs a reviewed request. Reject
  any explicit preset ID/version/locale combination that disagrees with the immutable catalog.
  [US3]

### Key Entities *(include if feature involves data)*

- **Agent grant**: Owner/client, disclosed scopes, expiry/revocation; raw bearer never persisted.
- **Agent work request**: Work kind, explicit instructions, targets, input revisions/snapshots,
  durable lifecycle and bounded expiry.
- **Agent proposal**: Bound analysis/opportunities/materials, evidence, provenance, receipt and
  review outcome; never itself a confirmed fact.
- **Template preset**: Stable ID/version, family/locale/layout, photo policy, compatible
  document kinds and default style/sections; no personal content.
- **Application packet**: Existing dossier with template provenance, email and letter exports
  alongside CV, sources and evidence.
- **Reference import**: Chosen local source, parsed candidates and review decisions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Fictional user completes discovery, analysis, reviewed tailoring and packet
  export with no local model and no direct cloud API in CareerOS.
- **SC-002**: Both documented client configurations pass initialization, tool listing,
  scoped context retrieval and submission against the open backend in contract tests.
- **SC-003**: All unauthorized/revoked/expired/foreign/invalid/stale/conflicting fixtures fail
  without confirmed-record mutations or sensitive error output.
- **SC-004**: All nine presets preview/export with checked text, order, A4 and page budgets.
  Representative pages from all three layouts and letters pass visual QA with no clipping,
  overlap, blank overflow pages or broken glyphs.
- **SC-005**: Switching and acceptance preserve all approved fixture content; retries create
  no duplicates and failed writes roll back.
- **SC-006**: Fictional Career reference import produces reviewed facts and a reusable packet,
  without modifying source files or embedding personal content in presets.
- **SC-007**: Full backend/frontend/Rust/migration gates run with exact results recorded; no
  unresolved high-severity review defect is declared complete.

## Assumptions

- Creating suitable jobs means finding/importing real vacancies and preparing applications.
- Codex/Claude is installed/authenticated separately; its own client controls subscription/model.
  CareerOS does not implement hosted APIs or promise unattended subscription access.
- MCP is client-driven: CareerOS queues work; the user invokes the connected agent. No hidden
  launch or assumption that an MCP server can initiate model inference.
- ../Career is a read-only workflow reference, not permission for indiscriminate migration.
  Selected imports are reviewed; credential/history files are excluded.
- Reuse vault, canvas, application, dossier and portability services; refactor coupling around
  these workflows. Unrelated branding and release work is outside scope.
- Templates recreate reusable structures without private data; arbitrary executable HTML/CSS
  plugins are outside scope.
- Commit, push, PR and release publication are not requested. Tests/builds are required;
  packaging/environment limits are reported accurately.
