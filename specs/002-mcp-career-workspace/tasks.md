# Tasks: MCP Career Workspace and Template Studio

**Input**: spec.md, plan.md, research.md, data-model.md, contracts/
**Tests**: Required by owner. After delegated-engine quota exhaustion, the owner explicitly
authorized the coordinating Codex agent and its subagents to implement and edit tests directly.
**Organization**: Stories are independently reviewed; coordinator maintains specs and findings.

## Phase 1: Setup

- [x] T001 Inspect existing CareerOS and read-only ../Career workflow; record research.md.
- [x] T002 Amend constitution 2.0.0 and AGENTS.md before specifying the new boundary.
- [x] T003 Generate complete spec.md, plan.md, data-model.md, contracts/ and quickstart.md with installed GitHub Spec Kit workflows.
- [x] T004 Record pre-change gates and environment limitations in validation.md.

## Phase 2: Foundation

- [x] T005 Add strict request/result/evidence DTOs in backend/agent_work/schemas.py and tests/backend/agent_work/test_contracts.py.
- [x] T006 Add owned work/proposal persistence models and additive Alembic migration in backend/agent_work/models.py and backend/migrations/versions/.
- [x] T007 Add migration tests preserving old grants/documents and upgrade/downgrade/upgrade in tests/backend/agent_work/test_migrations.py.
- [x] T008 Extend explicit grant scopes/disclosure with old-scope compatibility in backend/automation/{schemas,grants}.py and tests/backend/automation/.
- [x] T009 Implement bounded context snapshots, contact redaction, input digest and target revisions in backend/agent_work/context.py with tests.
- [x] T010 Implement durable work lifecycle, list/create/cancel/reject and safe errors in backend/agent_work/service.py with ownership/CAS/expiry tests.
- [x] T011 Implement evidence/result validation, stale checks and replay-safe proposal receipt in backend/agent_work/validation.py and proposal_service.py with negative tests.

## Phase 3: US1 - Connected agent workspace

**Goal**: Owner-created work can be returned through MCP with the app open and no local model.
**Independent Test**: Actual MCP session initializes, reads bounded context, submits, then fails after revocation.

- [x] T012 [US1] Add grant-only fixed bridge routes in backend/api/routes/agent_bridge.py and narrow desktop middleware integration, testing JWT/session-token rejection, Host/origin/loopback and maintenance.
- [x] T013 [US1] Add owner queue/review routes in backend/api/routes/agent_work.py, register schemas/routes and verify no grant can invoke owner actions.
- [x] T014 [US1] Add canonical loopback bounded HTTP client in backend/automation/desktop_client.py; test redirects/proxy/path/URL/body/timeouts.
- [x] T015 [US1] Add workspace MCP tools in backend/automation/workspace_mcp.py and --desktop-url dispatch in mcp_server.py while preserving offline read-only behavior.
- [x] T016 [US1] Test real MCP SDK initialize/list/call, scope metadata, submission and revoked/expired/canceled work in tests/backend/automation/test_workspace_mcp.py.
- [x] T017 [US1] Add installed console-capable bridge launcher/entrypoint, private atomic restart-aware connection descriptor and actual command discovery in desktop/, backend/desktop/, scripts/build*, frontend/src-tauri/ with packaged stdio and restart tests.
- [x] T018 [US1] Extend Agent Access disclosure, scope choices and Codex/Claude setup in frontend/src/features/agent-access/ with token-free configuration tests.
- [x] T019 [US1] Add localized accessible work queue/create/detail/review state UI in frontend/src/features/agent-work/ and API client integration.
- [x] T020 [US1] Integrate external workflow navigation and truthful local-model gates in frontend/src/app/AuthenticatedWorkspace.jsx without blocking manual/history work.
- [x] T021 [US1] Test queue/create/cancel/review/revoke UI and documented configurations with frontend unit/browser tests.

## Phase 4: US2 - Opportunity discovery and analysis

**Goal**: Evidence-based agent findings become reviewed opportunities in the existing pipeline.
**Independent Test**: Proposed listings and a duplicate produce one accepted application; stale/foreign results fail.

- [x] T022 [US2] Implement discovery/source provenance and hard-gate/score contracts in backend/agent_work/ with fixture coverage.
- [x] T023 [US2] Implement transaction-safe opportunity acceptance reusing backend/search catalog/manual capture and backend/applications identity, in backend/agent_work/acceptance.py.
- [x] T024 [US2] Persist external-agent analysis provenance without spoofing local attestation; integrate read/display paths in backend/ai/attestation.py and relevant job projections.
- [x] T025 [US2] Add search intent/job analyze request actions and cited gate/score/proposal review in frontend/src/features/agent-work/ and job UI.
- [x] T026 [US2] Test duplicate/retry acceptance, changed adverts/profile, source injection, owned references, concurrent writers and rollback in tests/backend/agent_work/.
- [x] T027 [US2] Verify browser journey discovery -> review -> existing application timeline without local model.

## Phase 5: US3 - Reusable template studio

**Goal**: Nine versioned presets, three layouts and content-preserving template switching.
**Independent Test**: Preview/export every preset, switch/duplicate/restore without losing approved content.

- [x] T028 [P] [US3] Define nine immutable presets and metadata in backend/resumes/templates.py with catalog/policy tests.
- [x] T029 [US3] Add template ID/version/locale persistence and migration, compatible legacy snapshots and API DTOs in backend/resumes/ and tests/backend/resumes/.
- [x] T030 [US3] Implement content-preserving preset selection through draft/canvas/duplicate/restore/publication in backend/resumes/ with concurrency/roundtrip tests.
- [x] T031 [US3] Render distinct ATS, Swiss photo and Swiss operational layouts, localized labels and matched letter style in backend/resumes/renderers/; preserve photo/text sanitation.
- [x] T032 [US3] Add template catalog/filter/cards/preview and content-preserving selection in frontend/src/features/resume-studio/ with accessibility tests.
- [x] T033 [US3] Test all nine preset PDF/DOCX visible content (not titles only), A4 in every section, page budgets, Unicode, actual safe hyperlinks, table text, long text, placeholders and photos in tests/backend/resumes/test_template_quality.py; fix confirmed legacy export defects.
- [x] T034 [US3] Verify old published artifact hashes and template metadata through migrations/restore/backup in tests/backend/resumes/ and tests/backend/portability/.

## Phase 6: US4 - Application material and packets

**Goal**: Cited agent proposals become reviewed CV/letter/email/answer drafts and local packet exports.
**Independent Test**: Full material request -> proposal -> edit/accept -> PDF/DOCX/packet, unchanged unsent state.

- [x] T035 [P] [US4] Extract existing dossier orchestration from backend/applications/service.py into focused modules with characterization tests before extending it.
- [x] T036 [US4] Add strict material proposal DTOs/grounding for CV/letter/email/answers in backend/agent_work/, plus migrated unpublished dossier-to-CV-draft binding in backend/applications/ and tests/backend/agent_work/test_materials.py.
- [x] T037 [US4] Accept material proposals atomically into existing CV/dossier drafts, checking all source/destination revisions, in backend/agent_work/material_acceptance.py.
- [x] T038 [US4] Add local paired letter PDF/DOCX and safe offline email draft artifacts in backend/applications/ with text/headers/attachments/rollback tests.
- [x] T039 [US4] Extend dossier packet manifest/export and quality blockers for stale content/placeholders/evidence/missing files in backend/applications/exports.py and focused publication modules.
- [x] T040 [US4] Add materials request/review/edit and letter/email selection/export UI in frontend/src/features/applications/ with localized accessible controls.
- [x] T041 [US4] Test edit-after-request, edit-after-review, duplicate acceptance, failed intermediate writes and no agent publish/send permissions in tests/backend/agent_work/ and applications/.
- [x] T042 [US4] Verify complete browser opportunity-to-packet journey without local model, including readable artifacts and unsent application state.

## Phase 7: US5 - Reference reuse

**Goal**: Explicit selected Career-format references become reviewed candidates without source mutation.
**Independent Test**: Fictional profile/narrative/goals Markdown import -> confirmation -> template packet.

- [x] T043 [P] [US5] Extend bounded selected text/Markdown import and source-role persistence/typed preference candidates per contracts/reference-import.md in backend/career/, with migration, unsafe-input and unchanged-source tests.
- [x] T044 [US5] Add source-role/import preview and confirmation UI in frontend/src/features/career-profile/ with reviewed-candidate behavior.
- [x] T045 [US5] Test fictional Career-shaped reference flow and document supported imports in docs/daily-driver.md.

## Phase 8: Cross-cutting validation and convergence

- [x] T046 Integrate new work/proposal/template/material records into backend/portability and reset/restore/erasure, with bounded manifests, ownership and rollback tests.
- [x] T047 Update README.md, docs/privacy.md, docs/architecture.md and agent usage docs with truthful external disclosure, installed/developer setup and end-to-end workflow.
- [x] T048 Add a versioned offline golden set for discover/analyze/materials in tests/backend/agent_work/fixtures/ with expected evidence validity, gates, fit-v1 scores, unsupported-claim rejection and quality metrics; run it plus existing security/evidence/portability/AI evaluations and record exact results in validation.md.
- [x] T049 Render fictional examples and visually inspect all three CV layouts and letter variants; record template/page/text evidence in validation.md (outputs in OS temp).
- [x] T050 Run full ruff/mypy/pytest, npm test/lint/build/e2e, cargo fmt/clippy/test and temp migration cycle; record failed/skipped checks exactly in validation.md.
- [x] T051 Coordinator performs independent code/behavior review and Spec Kit analysis, writing analysis.md; route every defect to an owner-authorized implementation agent with tests required.
- [x] T052 Authorized implementation model corrects all review defects; rerun justified checks and update validation.md.
- [x] T053 Coordinator runs Spec Kit convergence, appends any remaining unbuilt work and verifies closure in convergence.md.
- [x] T054 Verify final diff preserves user data/changes, reference directory and no stage/commit/push/PR/release; report outcome and limitations.

## Dependencies and parallel opportunities

Foundation T005-T011 precedes agent transport/acceptance. T012-T018 can proceed before UI.
US3 T028-T034 is independent of agent foundation except final material integration; its migration
must follow the new head. US4 dossier extraction T035 can proceed independently before proposals.
US2 and US4 acceptance depend on T009-T013. US5 can proceed independently using existing import.
T046 requires schema decisions from all slices. T048-T054 only close after all stories.

Parallel example: one Spark process owns agent backend, one owns template/CV backend+UI. Shared
migrations/portability/applications and UI shell changes require explicit handoff and ordered
migration parent revisions. No two models edit shared files simultaneously.

## Implementation strategy

Implement thin complete slices, test and review each before broad gates. Do not check tasks off
based on existence of stubs or successful mocked calls alone. The owner now authorizes direct
implementation by the coordinating Codex agent and its subagents; retain file ownership between
parallel workers and independent review. Temporary prompts, outputs and rendered artifacts live
under OS temp, never in repository scratch folders.

## Phase 9: Convergence

Assessment after provider-quota interruption, 2026-09-13. These are traceable repair/closure
tasks, not a claim that earlier unchecked tasks are complete. Review findings contain reproducible cases and diagnostic
logs; fixes require stronger tests than the initial mocked/happy-path suites.

- [x] T055 CRITICAL Restore real backend bootstrap and correct partial application imports/ownership APIs in backend/applications/{letters,dossier_service}.py; resolve RA000 and rerun collection before any acceptance claims, per FR-018/SC-001 and existing offline/manual usability (closed from a prior contradiction).
- [x] T056 CRITICAL Close detailed-context and transport authority gaps R001-R003,R013-R018,R025,R033-R035,R038-R042 with owned bounded snapshots, correct preferences, exact methods/routes, canonical URLs/UUIDs, streaming/deadlines and content-free errors, per FR-003/FR-004/FR-014/FR-017 and Constitution privacy/security boundaries (closed from prior contradictions).
- [x] T057 CRITICAL Implement live-revision validation, true database CAS, expiry and authenticated replay handling plus substantive evidence/fit-v1 policy R004-R005,R019,R024,R026-R032; exercise independent migrated SQLite connections and late rollback, per FR-005/FR-007/FR-008/FR-009 and advisory-confirmation boundary (closed from prior contradictions).
- [x] T058 CRITICAL Add new agent/reference/template/dossier/packet records to bounded versioned portability and reset/erasure; null restored live grants, remap target Job FKs, preserve historical snapshots/bytes and old photo preset backfill, verify packet journal ownership/rollback and RA001-RA002, per FR-011/FR-017/FR-019 and Constitution portability/erasure boundaries (closed from prior missing coverage).
- [x] T059 Align frontend wire DTOs with real serialized API schemas and repair full review visibility, disclosure, selection, pagination/refresh and asynchronous modal identity R006-R012,R020-R023; test no-model opportunity-to-timeline with actual backend guards, per FR-001/FR-002/FR-018 and US1/US2 acceptance criteria (closed from prior partial coverage).
- [x] T060 Complete all nine preset defaults, three truthful distinct layouts, content/evidence/photo preservation, genuine Unicode/table/hyperlink/A4/page quality and accessible gallery; resolve RT001-RT016 through actual draft publish/restore tests and visual QA, per FR-010/FR-011/FR-012/FR-022 and SC-004/SC-005 (closed from prior partial coverage).
- [x] T061 Complete strictly typed grounded materials and atomic CV/dossier draft acceptance, paired letter/email options and immutable enhanced packet publication with safe populated migration/downgrade policy; do not mark materials accepted without writes; close RA000-RA002 and full unsent browser journey, per FR-009/FR-013/FR-015 and SC-001/SC-005 (closed from prior partial coverage).
- [x] T062 Repair whole-value preference parsing and DOCX traversal RR001-RR002, validate combined accepted preferences and owner-save workflow, fix the failing new CareerProfilePage test with correct behavior, per FR-016/FR-018 and SC-006 (closed from prior partial coverage).
- [x] T063 Implement distributed console launcher, private restart-aware descriptor and dedicated token-free native discovery, integrate --connection-file in the existing MCP client, then test actual frozen stdio and backend restart; preserve headless lease, per FR-002/FR-021 and SC-002 (closed from prior missing coverage).
- [x] T064 Replace inadequate mocked/title-only verification with real strict MCP schemas R036, no-model/desktop-lease/SQLite integration R037, versioned golden cases, all material visual QA and exact full gates; finish truthful user/privacy/setup docs and rerun independent analysis/convergence, per FR-020 and SC-001 through SC-007 (closed from prior partial coverage).
- [x] T065 [US4] Close packet review RA003-RA014 in backend/applications/ and application/agent tests: preserve committed ZIPs on cleanup/uncertain-commit errors, recover owned journals under lock, implement independent-session dossier CAS without internal rollback, prove approved CV binding/readiness and complete saved-payload equality, preserve domain exception types and schema-specific immutable downloads, and render complete escaped letter/email artifacts; retain legacy schema 1/2 byte evidence, per US4 scenarios 7-9 and FR-009/FR-013/FR-015/FR-017 (closed from prior contradictions). Closure followed T055 and revalidated the shared mutation/storage contracts across T037/T058 integration.
- [x] T066 [US5] Close reference review RR003-RR009 with bounded explanatory parsing, validation of entire merged preferences, explicit scalar-conflict choice, preserved failed selection and request/revision-safe upload/save UI; add deferred-response tests for preference data loss and source replacement plus real DTO limit cases, per US5 scenarios 4-6 and FR-016/FR-018 (closed from prior partial coverage). Closure included T062 and revalidated the T045/T042 browser acceptance paths.

## Phase 10: Pre-merge audit corrections

- [x] T067 [US3] Reject every preset ID/version/locale mismatch in the shared resume resolver and cover direct, draft-write and generate schema boundaries, per US3 scenario 6 and FR-022.
- [x] T068 [US4] Preserve an exact current accepted-external analysis in application snapshots while continuing to quarantine stale or unattested matches; add sanitization and real acceptance-to-application regressions, per US4 scenario 10 and FR-007.
- [x] T069 [US1] Add an explicit CLI grant disclosure acknowledgement, propagate it to issue_grant and prove omission fails closed while acknowledged context/proposal scopes succeed, per FR-003.
- [x] T070 Apply shared strict JSON decoding to outer archive, nested packet restore and packet download boundaries; reject duplicate nested manifest keys with valid recomputed digests in restore and download tests, per FR-017.
- [x] T071 Remove committed personal absolute-path evidence, rerun targeted and complete gates after T067-T070, close independent review/convergence, commit the complete feature and fast-forward the authorized branch into local main, per FR-020 and SC-007.
