---

description: "Dependency-ordered implementation tasks for CareerOS Local desktop migration"
---

# Tasks: CareerOS Local Desktop Career Agent

**Input**: Design artifacts in `specs/001-desktop-career-agent/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`,
`quickstart.md`, and `.specify/memory/constitution.md`

**Tests**: Mandatory. Every story starts with executable failure cases and finishes with an
independent acceptance run. Network is denied unless the test explicitly covers consented model
or job-source acquisition.

**Format**: `[ID] [P?] [Story?] Description with exact path`

## Phase 1: Setup and product reset

**Purpose**: Establish the renamed product, native workspace and reproducible toolchain.

- [X] T001 Rename Python, npm, OCI and application identifiers to CareerOS Local in `pyproject.toml`, `frontend/package.json`, `frontend/package-lock.json`, `Dockerfile`, `docker-compose.yml`, `.env.example`, and `alembic.ini`
- [X] T002 [P] Replace scratch-output conventions and generated-path rules in `.gitignore`, `.dockerignore`, `.github/workflows/ci.yml`, and `.pre-commit-config.yaml`
- [X] T003 Initialize the Tauri v2 crate and strict application configuration in `frontend/src-tauri/Cargo.toml`, `frontend/src-tauri/build.rs`, `frontend/src-tauri/tauri.conf.json`, and `frontend/src-tauri/capabilities/main.json`
- [X] T004 Add locked Tauri frontend dependencies and desktop scripts in `frontend/package.json` and `frontend/package-lock.json`
- [X] T005 [P] Generate platform icon assets from `frontend/public/careeros.svg` into `frontend/src-tauri/icons/`
- [X] T006 [P] Add the pinned managed-runtime and model catalog in `backend/inference/model_catalog.json` and catalog loader in `backend/inference/catalog.py`

---

## Phase 2: Foundational privacy, contracts and audit data

**Purpose**: Blocking interfaces shared by every user story.

- [X] T007 [P] Add tests rejecting legacy product names, remote-AI clients and hidden inference egress in `tests/backend/security/test_product_identity.py` and `tests/backend/security/test_local_inference_boundary.py`
- [X] T008 [P] Add desktop environment, app-data path and loopback-binding tests in `tests/backend/desktop/test_settings.py`
- [X] T009 Implement desktop settings validation and process-safe path resolution in `backend/desktop/settings.py` and `backend/desktop/__init__.py`
- [X] T010 Implement per-launch session-header middleware with constant-time comparison in `backend/desktop/session.py` and register it in `backend/main.py`
- [X] T011 [P] Define versioned compact-model task contracts and validation error codes in `backend/ai/contracts.py`, `backend/ai/task_specs.py`, and `backend/ai/__init__.py`
- [X] T012 [P] Add AI execution/evaluation ORM entities and repository methods in `backend/ai/models.py`, `backend/ai/repository.py`, and `backend/models/__init__.py`
- [X] T013 Create and round-trip-test the AI audit migration in
  `backend/migrations/versions/` and `tests/backend/integration/test_ai_audit_migration.py`
- [X] T014 Implement redacted AI execution audit recording in `backend/ai/audit.py` and cover content exclusion in `tests/backend/ai/test_audit.py`

**Checkpoint**: Desktop requests can be authenticated, local paths are safe, structured contracts
exist, and content-free AI audit data can migrate without modifying career records.

---

## Phase 3: User Story 1 — Install and own a private workspace (Priority: P1) 🎯 MVP

**Goal**: A clean-machine native application owns its sidecar, vault and shutdown lifecycle.

**Independent Test**: Build the frozen backend and native development app, launch with no Docker or
system Python, create data, restart offline, and confirm zero orphaned child processes.

### Tests for User Story 1

- [X] T015 [P] [US1] Add frozen-entry argument, migration-backup, readiness and ordered
  graceful-watchdog/hard-timeout tests in `tests/desktop/test_backend_entry.py`
- [X] T016 [P] [US1] Add Rust unit tests for random-port allocation, sidecar arguments,
  bootstrap redaction, bounded restart, token-authenticated shutdown transport and idempotent exit
  state in `frontend/src-tauri/src/lifecycle.rs` and `frontend/src-tauri/src/commands.rs`
- [X] T017 [P] [US1] Add frontend bootstrap/client session-header tests in `frontend/src/platform/desktop.test.js` and `frontend/src/lib/client.desktop.test.js`
- [X] T018 [P] [US1] Add packaged-process lifecycle acceptance coverage in `tests/desktop/test_packaged_lifecycle.py`

### Implementation for User Story 1

- [X] T019 [US1] Implement frozen backend CLI, environment initialization, migration
  backup/restore, desktop-only authenticated shutdown route, graceful Uvicorn drain and bounded
  parent watchdog in `desktop/backend_main.py`, `backend/api/routes/desktop.py` and
  `backend/api/api.py`
- [X] T020 [US1] Define reproducible PyInstaller analysis, data files and hidden imports in `desktop/careeros-backend.spec`
- [X] T021 [US1] Implement the verified one-folder resource build flow and optional non-distributed one-file diagnostic in `scripts/build_backend_sidecar.py`
- [X] T022 [US1] Implement Tauri random-port/session creation, single-instance backend spawn,
  readiness state, exit prevention, bounded graceful shutdown with forced fallback and Windows
  kill-on-close Job Object containment in `frontend/src-tauri/src/lifecycle.rs` and
  `frontend/src-tauri/src/lib.rs`
- [X] T023 [US1] Expose only the redacted `desktop_bootstrap` invoke contract in `frontend/src-tauri/src/commands.rs` and `frontend/src-tauri/src/lib.rs`
- [X] T024 [US1] Add desktop bootstrap splash, API reconfiguration and bounded readiness polling in `frontend/src/platform/desktop.js`, `frontend/src/components/DesktopBoot.jsx`, and `frontend/src/main.jsx`
- [X] T025 [US1] Refactor the API client to support a runtime loopback base URL and session header without weakening browser validation in `frontend/src/lib/client.js`
- [X] T026 [US1] Add deterministic desktop-safe routing and external navigation handling in `frontend/src/App.jsx` and `frontend/src/platform/navigation.js`
- [X] T027 [US1] Add native development/build commands and sidecar preparation to `frontend/package.json`, `scripts/package_desktop.ps1`, and `scripts/package_desktop.sh`
- [X] T028 [US1] Add native build and artifact-smoke jobs for Windows, macOS and Linux in `.github/workflows/desktop-release.yml`

**Checkpoint**: User Story 1 passes independently and is the distributable desktop MVP.

---

## Phase 4: User Story 2 — Complete career profile and direction (Priority: P1)

**Goal**: The vault captures detailed, valid, evidence-linked career history and actionable goals.

**Independent Test**: Create every supported fact family and a goal with milestones/actions, trigger
date conflicts, restart, and verify completeness, relationships and progress are unchanged.

### Tests for User Story 2

- [X] T029 [P] [US2] Expand payload-schema, date-consistency and fact-provenance tests in `tests/backend/career/test_payloads.py` and `tests/backend/career/test_service.py`
- [X] T030 [P] [US2] Add profile completeness and goal milestone interaction tests in `frontend/src/features/career-profile/CareerProfilePage.test.jsx`

### Implementation for User Story 2

- [X] T031 [US2] Complete typed payload validation for experience, achievements, skills, projects, education, credentials, languages and activities in `backend/career/payloads.py` and `backend/career/schemas.py`
- [X] T032 [US2] Add deterministic completeness, temporal-conflict and missing-evidence analysis in `backend/career/completeness.py` and `backend/career/service.py`
- [X] T033 [US2] Extend goal payloads with target constraints, milestones, actions, skill gaps and progress validation in `backend/career/goal_schemas.py` and `backend/career/service.py`
- [X] T034 [US2] Surface detailed sections, evidence state, completeness and goal progress with keyboard-safe controls in `frontend/src/features/career-profile/`

**Checkpoint**: User Story 2 is independently usable as a detailed local career vault.

---

## Phase 5: User Story 3 — Generate and manually refine truthful resumes (Priority: P1)

**Goal**: Profile facts produce ATS/photo resumes that remain fully editable on a safe canvas.

**Independent Test**: Generate both variants, edit/reorder/resize/hide blocks, undo/redo, save and
restore versions, export PDF/DOCX, and verify evidence, text extraction and overflow behavior.

### Tests for User Story 3

- [X] T035 [P] [US3] Expand automatic-selection, claim-grounding and template-policy tests in `tests/backend/resumes/test_generator.py` and `tests/backend/resumes/test_claims.py`
- [X] T036 [P] [US3] Add canvas keyboard, direct-edit, geometry, undo and overflow tests in `frontend/src/features/resume-studio/canvas/ResumeCanvas.test.jsx` and `frontend/src/features/resume-studio/canvas/canvasReducer.test.js`
- [X] T037 [P] [US3] Add PDF/DOCX text-order, metadata and overflow integration tests in `tests/backend/resumes/test_renderers.py`

### Implementation for User Story 3

- [X] T038 [US3] Harden deterministic profile/goal-based fact selection and evidence maps in `backend/resumes/generator.py` and `backend/resumes/claim_service.py`
- [X] T039 [US3] Complete versioned canvas schema, bounded layout validation and ATS/photo invariants in `backend/resumes/canvas_schemas.py`, `backend/resumes/canvas_validation.py`, and `backend/resumes/canvas.py`
- [X] T040 [US3] Complete direct editing, keyboard movement, reorder, visibility, sizing, zoom, page guides and undo/redo in `frontend/src/features/resume-studio/canvas/`
- [X] T041 [US3] Harden local PDF/DOCX publishing, photo metadata stripping and pre-export quality gates in `backend/resumes/renderers/`, `backend/resumes/photos.py`, and `backend/resumes/publication_service.py`

**Checkpoint**: User Story 3 independently produces validated, editable career documents.

---

## Phase 6: User Story 4 — Accurate help from small local models (Priority: P2)

**Goal**: A user explicitly installs a compact local model and receives constrained, grounded,
measurably accurate assistance offline.

**Independent Test**: Install the pinned runtime/model, disconnect networking, run all golden task
families on the compact profile, and meet schema, evidence, hallucination and accuracy gates.

### Tests for User Story 4

- [x] T042 [P] [US4] Add catalog signature, platform selection, hash and unsafe-archive tests in `tests/backend/inference/test_catalog.py` and `tests/backend/inference/test_managed_runtime.py`
- [x] T043 [P] [US4] Add schema-constrained llama.cpp/Ollama adapter contract tests in `tests/backend/inference/test_structured_adapters.py`
- [x] T044 [P] [US4] Add BM25 ranking, context-budget and prompt-injection isolation tests in `tests/backend/ai/test_retrieval.py`
- [x] T045 [P] [US4] Add schema, grounding, semantic validation and single-repair tests in `tests/backend/ai/test_orchestrator.py` and `tests/backend/ai/test_grounding.py`
- [x] T046 [P] [US4] Add versioned synthetic golden cases and evaluator metric tests in `tests/ai/fixtures/`, `tests/backend/ai/test_evaluation.py`, and `tests/backend/ai/test_golden_contracts.py`
- [x] T047 [P] [US4] Add model setup/progress/cancellation UI tests in `frontend/src/features/local-model/LocalModelStatus.test.jsx` and `frontend/src/features/local-model/ModelManager.test.jsx`

### Implementation for User Story 4

- [x] T048 [US4] Generalize the local inference port for JSON Schema, metadata and runtime capabilities in `backend/inference/ports.py` and `backend/providers/llm/base.py`
- [x] T049 [US4] Implement the authenticated llama.cpp chat/list adapter and schema response format in `backend/inference/llama_cpp.py`
- [x] T050 [US4] Upgrade the Ollama adapter to the same schema contract and deterministic task options in `backend/inference/ollama.py`
- [x] T051 [US4] Implement atomic cancellable runtime/model download, safe extraction, verification, process health and bounded restart in `backend/inference/managed_runtime.py`
- [x] T052 [US4] Expose catalog, status, install, cancel and restart contracts in `backend/api/routes/local_model.py`, `backend/inference/service.py`, and `frontend/src/services/localModel.js`
- [x] T053 [US4] Implement deterministic bounded evidence ranking in `backend/ai/retrieval.py` and per-claim grounding checks in `backend/ai/grounding.py`
- [x] T054 [US4] Implement generate-validate-single-repair orchestration and content-free audit integration in `backend/ai/orchestrator.py`
- [x] T055 [US4] Migrate coach output to constrained claims/citations/confidence while preserving API compatibility in `backend/career/coach.py` and `backend/career/coach_schemas.py`
- [x] T056 [US4] Apply task schemas and semantic validators to profile normalization, search planning, job normalization, matching, critique and reranking through `backend/services/llm_service.py`
- [x] T057 [US4] Implement offline fixture validation, live compact-model execution and aggregate reports in `backend/ai/evaluation.py` and `backend/api/routes/ai_evaluations.py`
- [x] T058 [US4] Replace Ollama command-line instructions with consent, license, size, progress, cancellation and retry UI in `frontend/src/features/local-model/`

**Checkpoint**: User Story 4 passes offline on the pinned compact model and rejects unsupported output.

---

## Phase 7: User Story 5 — Carry, recover and erase the vault (Priority: P2)

**Goal**: Backups survive installation changes and explicit erasure removes only app-managed data.

**Independent Test**: Export a populated vault, restore into a clean desktop installation, compare
counts/hashes, reject a damaged archive without mutation, then erase app data without touching an
unrelated sentinel file.

### Tests for User Story 5

- [x] T059 [P] [US5] Add desktop app-data backup/restore and interrupted-upgrade tests in `tests/backend/portability/test_desktop_roundtrip.py`
- [x] T060 [P] [US5] Add managed model/temp erasure and unrelated-file safety tests in `tests/backend/career/test_desktop_deletion.py`

### Implementation for User Story 5

- [x] T061 [US5] Include AI audit schema, resume assets and manifest compatibility in `backend/portability/archive.py` and `backend/portability/manifest.py`
- [x] T062 [US5] Make restore transactional under the desktop vault lock with preflight and rollback in `backend/portability/restore.py` and `backend/desktop/lifecycle.py`
- [x] T063 [US5] Extend explicit deletion to managed model/runtime, sensitive staging and desktop vault paths in `backend/career/deletion.py` and `backend/inference/managed_runtime.py`
- [x] T064 [US5] Add desktop-native backup destination, restore source and erasure confirmation flows in `frontend/src/features/home/` and `frontend/src/services/portability.js`

**Checkpoint**: User Story 5 proves ownership, recovery and precise local erasure.

---

## Phase 8: Heavy refactor, documentation and production gates

**Purpose**: Remove migration debt, recreate operator/developer guidance and prove release quality.

- [x] T065 Split AI runtime policy, planning, profile normalization, job normalization, matching and reranking from `backend/services/llm_service.py` into `backend/ai/` and leave a compatibility facade below 300 lines
- [x] T066 Split acquisition, persistence, normalization, matching and finalization from `backend/services/search_service.py` into `backend/search/` and leave a compatibility facade below 300 lines
- [x] T067 Split provider-independent mapping domains from `backend/services/search/listing_utils.py` into `backend/search/normalization/` with snapshot parity tests in `tests/backend/search/`
- [x] T068 [P] Recreate owner, developer, security and architecture documentation in `README.md`, `AGENTS.md`, `SECURITY.md`, `docs/architecture.md`, `docs/development.md`, `docs/privacy.md`, and `docs/releasing.md`
- [x] T069 [P] Recreate focused backend and frontend contributor guides in `backend/README.md` and `frontend/README.md`
- [x] T070 Remove all obsolete Markdown/output artifacts and add a repository-hygiene test in `tests/backend/security/test_repository_hygiene.py`
- [x] T071 Run and fix Python lint, type checks, full pytest, migration round-trips and performance acceptance using `pyproject.toml`, `pyrightconfig.json`, and `tests/backend/`
- [x] T072 Run and fix frontend lint, full Vitest coverage build, Cargo format/clippy/test and native debug launch using `frontend/package.json` and `frontend/src-tauri/Cargo.toml`
- [x] T073 Generate and audit Python/npm/Cargo SBOMs, licenses and vulnerabilities in `.github/workflows/ci.yml` and `.github/workflows/desktop-release.yml`
- [x] T074 Build and smoke-test the Windows installer locally, recording only reproducible commands and truthful results in `specs/001-desktop-career-agent/release-evidence.md`
- [x] T075 Perform Spec Kit cross-artifact analysis and convergence, append any missing tasks to `specs/001-desktop-career-agent/tasks.md`, and execute them before release
- [x] T076 Rename the physical workspace directory to `careeros-local`, verify Git remote `ejupi-djenis30/careeros-local`, and rerun a clean status/build check from the new absolute path

---

## Dependencies & Execution Order

### Phase dependencies

```text
Setup -> Foundation -> US1 desktop
                    -> US2 profile
                    -> US3 resume
US2 + Foundation -> US4 AI
US1 + Foundation -> US5 portability
US2 + US3 -> US6 application readiness
US1..US6 -> Heavy refactor and release gates -> physical folder rename
```

- Setup and Foundation block every story.
- US1, US2 and US3 can be completed independently after Foundation.
- US4 relies on evidence entities from US2 but not on resume rendering.
- US5 relies on US1 app-data/vault locking but not on AI availability.
- Heavy refactor preserves facades until all story acceptance tests pass.

### Parallel opportunities

- T002, T005 and T006 touch independent setup surfaces.
- T007, T008, T011 and T012 establish separate foundational contracts.
- Each story's test files marked `[P]` can be authored before its implementation slice.
- US2 and US3 can proceed in parallel after Foundation; US4 adapter, retrieval and UI tests are independent.
- Documentation T068/T069 can proceed after interfaces stabilize while production gates run.

## Parallel examples

### User Story 1

```text
T015 frozen backend tests
T016 Rust lifecycle tests
T017 frontend bootstrap tests
T018 packaged lifecycle acceptance
```

### User Story 4

```text
T042 managed-runtime security tests
T043 adapter schema tests
T044 retrieval tests
T045 orchestration/grounding tests
T046 evaluator fixtures and metrics
T047 model-manager UI tests
```

## Implementation Strategy

### MVP first

1. Complete Setup and Foundation.
2. Complete US1 through T028.
3. Prove native install, launch, persistence, offline reopen and clean shutdown.
4. Keep existing profile/resume capabilities available while their story hardening proceeds.

### Incremental delivery

1. Native private workspace (US1).
2. Complete structured career vault and goals (US2).
3. Truthful auto-generated and manually editable resumes (US3).
4. Explicit managed model and measured compact-model AI (US4).
5. Desktop-grade portability and erasure (US5).
6. Remove facades/debt only under full regression coverage, then package and rename the folder.

## Task validation

- Task identifiers remain sequential through T231.
- User Story 1: 50 tasks.
- User Story 2: 11 tasks.
- User Story 3: 9 tasks.
- User Story 4: 27 tasks.
- User Story 5: 18 tasks.
- User Story 6: 10 tasks (T106–T115).
- User Story 7: 15 tasks (T116–T123 and T157–T163).
- User Story 8: 12 tasks (T132–T143).
- User Story 9: 6 tasks (T144–T149).
- User Story 10: 18 tasks.
- Setup, foundation, polish, convergence and release work: 55 tasks.
- Every task uses the required checkbox, sequential ID, appropriate story label and exact path.
- Suggested MVP scope: Setup + Foundation + User Story 1.

## Phase 9: Convergence

The suffixes `(contradicts)`, `(partial)` and `(missing)` preserve each finding's classification at
the start of the audit; they do not describe current status. A checked task records its remediation.

- [x] T077 CRITICAL add post-bundle native lifecycle, offline-reopen, vault-preservation and uninstall acceptance gates for the release matrix in `.github/workflows/desktop-release.yml` and `scripts/` per Constitution I/V/VII and SC-010 (contradicts)
- [x] T078 Add local source-text preview, deterministic fact candidates, explicit review/acceptance and provenance tests in `backend/career/sources.py`, `backend/api/routes/career_profile.py`, and `frontend/src/features/career-profile/SourceImporter.jsx` per FR-013 (partial)
- [x] T079 Implement resumable pause, resume, remove and replace operations for managed models across `backend/inference/managed_runtime.py`, `backend/api/routes/local_model.py`, and `frontend/src/features/local-model/` per FR-007 (partial)
- [x] T080 Add an evidence-grounded resume-tailoring AI contract and golden case, and record live evaluation peak memory/model-profile telemetry in `backend/ai/` and `tests/backend/ai/` per FR-027, FR-028 and SC-004 (missing)
- [x] T081 Add deny-by-default per-source job-network consent with API/UI controls and audit-safe tests in `backend/search/`, `backend/api/routes/`, and `frontend/src/` per FR-029 (missing)
- [x] T082 Add resume-draft autosave, explicit version names, version comparison and non-destructive restore across `backend/resumes/` and `frontend/src/features/resume-studio/` per FR-020 (partial)
- [x] T083 Harden structured diagnostic redaction and add cross-domain content-leak tests in `backend/core/logging.py` and `tests/backend/security/` per FR-033 (partial)
- [x] T084 Add automated accessibility and keyboard/focus gates for setup, profile, goals, resume canvas/export, model management and recovery in `frontend/src/` per FR-035 and SC-011 (partial)
- [x] T085 Enforce one desktop shell and one lifetime vault-writer lease with multi-process tests in `frontend/src-tauri/`, `desktop/backend_main.py`, and `tests/desktop/` per FR-031 and the multi-instance edge case (missing)
- [x] T086 Add disk-full and interrupted-write fault injection for profile, resume, backup and export writers in `backend/storage/`, `backend/portability/`, and `tests/backend/` per the durability edge cases (partial)
- [x] T087 Extend career-goal links to learning activities and immutable resume versions in `backend/career/goal_schemas.py` and `frontend/src/features/career-profile/goals/` per FR-012 (partial)

## Phase 10: Post-audit release hardening

- [x] T088 Delete user-scoped search profiles, jobs and learned preference signals during complete-vault erasure, and prove SQLite/WAL content removal without touching unrelated user data per FR-032 and SC-002
- [x] T089 Add a backward-compatible portable-archive version that round-trips search profiles, jobs, referenced scraped listings, preference signals and application-to-job relationships per FR-030 and SC-008
- [x] T090 Correct compact-model and packaged-lifecycle release commands, and run CI for the public `main` branch
- [x] T091 Add a truthful, demo-first OpenAI Build Week submission kit with repository hero/thumbnail assets, real product captures, a loopback-only demo seeder, judge quickstart, Codex/GPT-5.6 development notes and a sub-three-minute video script
- [x] T092 Complete the CareerOS identity migration for frontend events and refresh cookies while rotating and clearing the legacy cookie without breaking existing local sessions
- [x] T093 Harden the dependency-free Pages presentation with intrinsic-ratio product media, correct decorative-image accessibility validation, pull-request validation, an accurate demo password and reproducible icon generation from the SVG master
- [x] T094 Add an on-device English-default/Italian interface catalogue for login, shell, navigation and portfolio-demo surfaces, update the deterministic recorder to English and cover locale switching with frontend tests per FR-036 and SC-012

## Phase 11: Immutable v1.1 release contract

- [x] T095 Add strict stable-SemVer and coordinated seven-source v1.1.0 validation with invalid/prerelease regression cases in `scripts/check_release_versions.py` and `tests/backend/unit/test_release_versions.py`
- [x] T096 Canonicalize each smoke-tested native target into portable release names and emit exact per-target manifests/checksums in `scripts/release_contract.py` and `scripts/release_candidate.py`
- [x] T097 Assemble and independently validate the closed six-target candidate, deterministic evidence archive, canonical public `LICENSE`, public CycloneDX SBOMs, global manifest and SHA-256 inventory in `scripts/release_contract.py`
- [x] T098 Enforce GitHub-verified annotated-tag resolution, exact workflow source and stable default-branch containment in `scripts/release_github.py`
- [x] T099 Implement authenticated paginated release discovery and a contract-bound, idempotent publisher with safe partial-upload, ambiguous-transition recovery and a fresh sequence check immediately before promotion in `scripts/publish_github_release.py`
- [x] T100 Refactor `.github/workflows/desktop-release.yml` so manual/scheduled rehearsals are read-only, tag publications share a cross-tag mutex with running-tag cancellation disabled, publication is push-only, action/toolchain/runner/CLI provenance is pinned, and every release/SBOM attestation is independently verified
- [x] T101 Add adversarial candidate coverage, downloadable and packaged canonical-license omission/tamper/duplication, off-branch tag, publisher pagination/race, foreign-state, collision, crash/retry, immutability and latest-state tests in `tests/backend/release/`
- [x] T102 Bump all seven release metadata sources to v1.1.0 and curate `CHANGELOG.md`, `docs/releasing.md` and v1.1 release evidence without creating a tag or Release
- [x] T103 Run Python release tests, workflow-policy validation, actionlint, frontend/Rust release checks and repository diff validation; record only commands actually executed
- [x] T104 Perform final cross-artifact convergence against FR-037–FR-039 and SC-013 before the immutable version tag is authorized
- [x] T105 Map the canonical project `LICENSE` into every Tauri distribution and verify its exact bytes in mounted, extracted or installed MSI, NSIS, AppImage, DEB and DMG payloads before staging

## Phase 12: User Story 6 — Deterministic Application Readiness Pack

**Goal**: Turn a saved application into a practical local preflight with inspectable evidence,
corrective actions and reproducible exports. The score is a completeness index only; it MUST NOT
be presented as hiring probability, candidate quality or advice from a model.

**Independent Test**: Compare zero-data, incomplete and complete application reports; request the
same JSON and Markdown exports twice; verify exact byte/digest equality, ownership isolation and
the absence of local paths or authentication material.

- [x] T106 [US6] Amend the constitution and specify deterministic readiness outcomes, boundaries,
  acceptance scenarios and measurable export behavior in `.specify/memory/constitution.md` and
  `specs/001-desktop-career-agent/spec.md`
- [x] T107 [US6] Plan the bounded service, API, UI and no-migration approach in
  `specs/001-desktop-career-agent/plan.md`
- [x] T108 [US6] Implement stable readiness schemas, weighted completeness checks, evidence/action
  fields, canonical serialization and content fingerprints in `backend/applications/`
- [x] T109 [US6] Add user-scoped readiness and JSON/Markdown export routes with deterministic
  filenames and digest headers in `backend/api/routes/applications.py`
- [x] T110 [US6] Add Application Detail preflight state, accessible check presentation and local
  downloads in `frontend/src/features/applications/`, `frontend/src/services/applications.js`,
  `frontend/src/i18n/messages.js` and `frontend/src/career-os.css`
- [x] T111 [US6] Cover zero-data, missing inputs, complete packs, foreign ownership, deterministic
  bytes, content disposition, UI rendering and downloads in backend/frontend tests
- [x] T112 [US6] Run proportional gates and record cross-artifact analysis and convergence in
  `specs/001-desktop-career-agent/application-readiness-analysis.md` and
  `specs/001-desktop-career-agent/application-readiness-convergence.md`
- [x] T113 [US6] Add an expected-revision preparation PATCH with a content-free append-only audit
  event, an editable application-pack form and direct Career Vault/Resume Studio remediation paths
  across `backend/applications/`, `backend/api/routes/applications.py` and
  `frontend/src/features/applications/`
- [x] T114 [US6] Verify each owned resume artifact through the contained storage read, immutable
  digest and declared byte length; replace metadata-only complete fixtures and cover deleted,
  corrupt, escaping, unreadable and size-mismatched files in `backend/applications/readiness.py`,
  `tests/backend/applications/test_application_api.py` and the deterministic demo seed
- [x] T115 [US6] Convert Application Detail into a portal-backed labelled modal with dynamic focus
  containment, Escape, opener restoration, inert/scroll-locked background and mobile-safe
  overscroll; prove semantics and keyboard traversal in `frontend/src/features/applications/`
- [x] T116 [US7] Amend the constitution, specification and plan for explicit-query privacy,
  user-namespaced manual captures, CAS application writes and lossless repeatable dossiers
- [x] T117 [US7] Make manual imports bounded, extra-forbidden, server-namespaced per user and
  idempotent; cover spoofed ids, retries, cross-user isolation and response visibility
- [x] T118 [US7] Remove CV and model-normalized planner fallbacks, preserve zero versus `NULL`
  limits through acquisition and cover unit plus provider-boundary behavior
- [x] T119 [US7] Route event append through revision CAS with the resulting stage in the update and
  prove exactly one winner with two file-backed SQLite/WAL sessions and a barrier
- [x] T120 [US7] Replay the maximum coherent task revision, reject regressions and conflicting
  duplicates, and load board next actions directly from projection columns
- [x] T121 [US7] Bound dossier evidence as UUIDs and add accessible repeatable requirement,
  question/answer and checklist rows with explicit partial-pair validation in English and Italian
- [x] T122 [US7] Update daily-driver, privacy, architecture and README guidance, including the
  no-historical-migration rationale for the still-unreleased manual importer
- [x] T123 [US7] Run all Python, React, Rust and Alembic gates and record analysis/convergence in
  `daily-driver-analysis.md` and `daily-driver-convergence.md`

## Phase 13: User Story 4 — Mandatory Local Analysis

**Goal**: Make the local LLM a real, required analysis capability without blocking ownership,
editing, portability, existing documents or deterministic application readiness.

- [x] T124 [US4] Amend constitution, specification and plan for truthful fail-closed analysis,
  required local readiness and preserved non-AI workflows
- [x] T125 [US4] Add stable content-free local-model readiness diagnostics and strict structured
  probe validation in `backend/inference/service.py` and `backend/api/routes/local_model.py`
- [x] T126 [US4] Require a ready local model before opportunity search starts and remove heuristic
  fallback results from `backend/search/matching.py` and `backend/search/finalization.py`
- [x] T127 [US4] Add an authenticated, keyboard-accessible required-model setup/readiness gate and
  explicit diagnostics in `frontend/src/features/local-model/`, services and bilingual catalogue
- [x] T128 [US4] Replace optional-AI product copy with accurate required-analysis language while
  retaining explicit model-free Vault, portability, document and readiness boundaries
- [x] T129 [US4] Cover health diagnostics, endpoint/model failures, fail-closed matching, API
  preconditions, UI setup/retry/unlock and accessibility in backend/frontend tests
- [x] T130 [US4] Update English-first owner, architecture, privacy and daily-driver documentation
  with local-model requirements, data boundaries and recovery steps
- [x] T131 [US4] Run proportional gates and record cross-artifact analysis and convergence in
  `mandatory-local-analysis-analysis.md` and `mandatory-local-analysis-convergence.md`

## Phase 14: User Story 8 — Private daily application agenda

**Goal**: Turn projected next actions into one deterministic, user-scoped daily queue without
replaying event payloads or requiring the local model.

- [x] T132 [US8] Amend constitution, specification and plan for deterministic classification,
  authenticated projection-only reads, explicit omission counts and model independence
- [x] T133 [US8] Add bounded agenda contracts and a focused projection-only service query in
  `backend/applications/schemas.py` and `backend/applications/agenda.py`
- [x] T134 [US8] Add the authenticated static agenda route before dynamic application routes and
  cover day boundaries, ordering, input bounds, query shape and cross-user isolation
- [x] T135 [US8] Add an independently loaded, keyboard-operable agenda to Applications with
  English/Italian copy and existing dialog navigation
- [x] T136 [US8] Update owner and daily-driver documentation with agenda behavior and boundaries
- [x] T137 [US8] Run proportional gates and record cross-artifact analysis and convergence in
  `daily-agenda-analysis.md` and `daily-agenda-convergence.md`

## Phase 15: User Story 8 — Daily agenda review hardening

- [x] T138 [US8] Amend constitution, specification, plan and tasks for one-snapshot reads,
  DST-correct day boundaries, refresh lifecycle, accessible relationships and 320 px/AA evidence
- [x] T139 [US8] Replace the two-query agenda read with one CTE/window statement, translate schema
  validation failures to 422 and cover concurrent/interleaved snapshot coherence
- [x] T140 [US8] Replace fixed offsets with a browser-calculated next-local-midnight instant,
  validate its safe window in the backend and update OpenAPI/contracts/tests
- [x] T141 [US8] Refresh on focus, visible-state restoration, next deadline and local midnight with
  abort/timer cleanup tests and an appropriate agenda read rate limit
- [x] T142 [US8] Associate visible agenda labels/descriptions, harden functional contrast and prove
  non-overlapping 320 px geometry in real Chromium
- [x] T143 [US8] Benchmark/query-plan the bounded statement, run proportional gates and update
  daily-agenda analysis/convergence with exact evidence

## Phase 16: User Story 9 — Backup assurance center

**Goal**: Let a user prove a portable backup is structurally usable before deleting anything, while
keeping inspection content-free and restore explicitly separate.

- [x] T144 [US9] Amend constitution, specification, plan and tasks for non-mutating inspection,
  content-free response fields, honest trust copy and verified destination writes
- [x] T145 [US9] Extract reusable archive preflight, validate application projections before writes,
  add the bounded inspection response and authenticated rate-limited endpoint
- [x] T146 [US9] Add adversarial, historical-version, populated-vault and complete zero-mutation
  backend coverage
- [x] T147 [US9] Add distinct verify/restore UI, English/Italian summary copy and service tests
- [x] T148 [US9] Make the native backup destination write temporary, digest-verified, rollback-safe
  and covered by frontend/platform fault tests with the minimum filesystem permissions
- [x] T149 [US9] Update owner documentation, run proportional gates and record backup-assurance
  analysis/convergence with exact evidence

## Phase 17: User Story 10 — Scoped CLI and MCP reads

**Goal**: Let a local user inspect bounded CareerOS state from a shell or coding agent without
sharing the vault, creating a second writer or exposing mutation tools.

**Independent Test**: Issue grants for two users and different scopes, negotiate through the
official MCP client in memory and over stdio, call every visible tool, and verify scope filtering,
typed bounded results, zero mutation, token redaction, expiry/revocation and exclusive-lease
failure while the desktop is active.

- [x] T150 [US10] Amend the specification and plan for source-installed CLI/MCP access, fixed read
  scopes, explicit agent disclosure, bounded DTOs and the existing exclusive vault lease
- [x] T151 [US10] Add the user-bound automation grant model, digest-only token persistence,
  expiry/revocation service and Alembic migration in `backend/automation/`,
  `backend/model_registry.py` and `backend/migrations/versions/`
- [x] T152 [US10] Add cwd-independent vault bootstrap, current-schema checks, authorization-only
  migration and per-read `desktop_instance_lease` ownership with grant revalidation in
  `backend/automation/runtime.py` and `backend/automation/mcp_server.py`
- [x] T153 [US10] Add the scoped read facade, JSON CLI entry point, MCP stdio server and
  Codex/Claude Code configuration output in `backend/automation/` and `pyproject.toml`
- [x] T154 [US10] Revoke active grants during restore and remove grant rows during complete vault
  erasure in `backend/portability/restore.py` and `backend/career/deletion.py`
- [x] T155 [US10] Cover token lifecycle, cross-user isolation, scope enforcement, zero mutation,
  output bounds, disclosure, client configuration and official MCP negotiation in
  `tests/backend/automation/`
- [x] T156 [US10] Update owner, privacy, architecture and development guidance and record
  cross-artifact analysis/convergence in `README.md`, `docs/` and
  `specs/001-desktop-career-agent/`

## Phase 18: User Story 7 — Durable application dossier drafts

**Goal**: Preserve incomplete dossier work in the private vault without weakening immutable
publication, cross-user isolation, backup validation or historical archive compatibility.

**Independent Test**: Create, reload, race, rebase and delete a multi-row draft; fail publication
after bundle preflight; round-trip format v6; inspect malformed draft rows; restore v1-v5; and
downgrade/upgrade the migration while verifying that no failed operation clears visible input.

- [x] T157 [US7] Amend specification, plan, tasks and OpenAPI for bounded private drafts,
  compare-and-swap writes, exact publication and format-v6 portability
- [x] T158 [US7] Add the one-to-one draft model, Alembic migration, bounded schemas and
  authenticated no-store CRUD routes in `backend/applications/` and `backend/api/routes/`
- [x] T159 [US7] Add debounced SQLite-backed autosave, restore, retry, conflict, discard and exact
  publish behavior with bilingual accessible states in `frontend/src/`
- [x] T160 [US7] Require unique nonblank stable row identities and consume a matching saved draft
  only in the immutable publication transaction
- [x] T161 [US7] Advance portable archives to v6, validate complete draft rows before writes,
  preserve v1-v5 compatibility and include draft cascade/erasure accounting
- [x] T162 [US7] Cover ownership, compare-and-swap, rebase, atomic failure, schema bounds,
  migration constraints, archive adversaries, round-trip, UI persistence and accessibility
- [x] T163 [US7] Run every release gate and record exact analysis and convergence evidence in
  `dossier-drafts-analysis.md` and `dossier-drafts-convergence.md`

## Phase 19: User Story 2 — CV-first first result

**Goal**: Let a non-developer start from an existing CV on a new account without first discovering
and completing an unrelated manual save, while preserving explicit fact review and local-only
source handling.

**Independent Test**: Open a new account whose profile GET returns 404, choose a supported source
document from the Home CV-first action, and verify the minimum revisioned profile write finishes
before the source upload. Accept one candidate, verify it is still `imported`, move focus to its
review section, confirm it manually and save. Repeat with profile-write and upload failures and
prove the file remains available for retry and no model API is called.

- [x] T164 [US2] Amend specification, plan and tasks for explicit CV-first bootstrap ordering,
  retry preservation, unconfirmed candidates and keyboard-operable review
- [x] T165 [US2] Add the Home CV-first/manual choice and make first-use source import persist the
  minimum profile before the existing bounded local upload
- [x] T166 [US2] Preserve the selected file across failures, expose explicit candidate review and
  add accurate English/Italian local-only first-use copy
- [x] T167 [US2] Cover operation ordering, no-upload failure, retry state, existing profiles,
  imported status, focus and accessibility in focused frontend tests
- [x] T168 [US2] Update first-use owner documentation, run proportional gates and record exact
  analysis/convergence evidence

## Phase 20: User Story 10 — Desktop Agent Access center

**Goal**: Let a desktop user issue, inspect and revoke the existing scoped read grants without
handling the vault directly or weakening the source-installed CLI/MCP boundary.

**Independent Test**: Sign in as each of two users, create differently scoped grants after password
re-authentication, verify one-time non-cacheable bearer delivery and metadata-only listing, then
revoke one grant. Exercise copy/dismiss/unmount behavior in the renderer and prove no bearer enters
browser storage, logs, later API responses or the other account.

- [x] T169 [US10] Amend constitution, specification, plan and tasks for password-confirmed desktop
  grant management, one-time non-cacheable secrets and transient renderer handling
- [x] T170 [US10] Add bounded create/list/revoke API contracts and authenticated per-account
  reauthentication protection that preserves emergency revocation, reuses
  `backend/automation/grants.py` and never persists bearers
- [x] T171 [US10] Add a lazy Agent Access workspace page, navigation, English/Italian copy,
  transient token handling, explicit copy, lifecycle status and source-install guidance
- [x] T172 [US10] Cover password verification, cross-user isolation, outermost no-store headers,
  active-grant visibility, emergency revocation, token non-reappearance, idempotent revocation,
  cleanup, focus restoration, keyboard access and failure preservation in focused tests
- [x] T173 [US10] Update README, privacy and daily-driver guidance and record exact cross-artifact
  analysis/convergence in `specs/001-desktop-career-agent/`
- [x] T174 [US10] Run proportional Python/React/security gates, repository hygiene and diff checks;
  record only commands actually executed

## Phase 21: User Story 1 — Mobile workspace navigation isolation

**Goal**: Make the mobile workspace drawer a complete modal navigation surface without changing
the persistent desktop sidebar or adding a runtime, permission or network boundary.

**Independent Test**: Open the workspace menu at mobile width, traverse it in both directions,
attempt to reach obscured content, close it through Escape, navigation and a desktop resize, and
verify focus, body scrolling and accessibility state are restored. Repeat the CSS geometry check
at 320, 375, 991 and 1,280 px with reduced motion enabled.

- [x] T175 [US1] Amend constitution, specification, plan and tasks for modal mobile navigation,
  inert background content, scroll/focus restoration and reduced-motion acceptance
- [x] T176 [US1] Implement modal semantics, inert workspace isolation, body-scroll locking,
  focus containment and route/resize cleanup in `frontend/src/app/WorkspaceShell.jsx` and
  `frontend/src/components/Layout/Sidebar.jsx`; remove the unused Bootstrap JavaScript entrypoint
  only after a repository-wide dependency scan
- [x] T177 [US1] Cover modal semantics, forward/reverse focus wrap, Escape, opener restoration,
  inert state, scroll restoration, non-focusable scrim, route changes, resize and unmount in
  `frontend/src/app/WorkspaceShell.test.jsx` and `frontend/src/components/Layout/Sidebar.test.jsx`
- [x] T178 [US1] Add real-Chromium mobile/desktop geometry, overflow and reduced-motion validation
  in `frontend/e2e/workspace-shell-responsive.mjs` and expose the focused npm script
- [x] T179 [US1] Run proportional and release frontend gates, record exact analysis in
  `mobile-workspace-navigation-analysis.md`, and converge the active Spec Kit artifacts in
  `mobile-workspace-navigation-convergence.md`

## Phase 22: User Story 1 — Measured offline renderer boot

**Goal**: Start the private login workspace with only the selected local language and auditable
icons, while enforcing byte, contrast, keyboard, CSP and offline recovery contracts.

**Independent Test**: Build the production renderer, open it at 390 px first in English and then
with Italian persisted, and prove each boot fetches one local catalogue and no icon font. Switch
English to Italian, exercise keyboard focus and disabled form state, run axe and inspect the
console. Force both locale imports to fail and prove a localized focused retry appears and performs
no automatic reload or repeated request.

- [x] T180 [US1] Amend constitution, specification, plan and tasks for executable renderer budgets,
  one-locale offline loading, explicit boot recovery, icon subsetting and enforceable CSP delivery
- [x] T181 [US1] Split English/Italian into independent bundled modules behind a deduplicating
  registry; add pending switch semantics, Italian-to-English fallback, localized focused boot retry
  and registry/StrictMode/failure/localization tests
- [x] T182 [US1] Generate an MIT-attributed SVG-mask subset from every explicit Bootstrap icon
  source token, reject computed/missing/stale names and remove the complete font entrypoint
- [x] T183 [US1] Raise language/privacy contrast, language touch targets and retain visible focus;
  move `frame-ancestors` to its enforceable Nginx header-only boundary and cover distribution
  contracts
- [x] T184 [US1] Enforce production entry/locale/CSS/initial raw and gzip budgets and add real
  Chromium EN/IT loading, axe, contrast, icon, focus, disabled-state and console validation
- [x] T185 [US1] Add a seven-day default cooldown to all Dependabot ecosystems, route release
  repository/tag/commit values through quoted environment variables, fix the proxy upstream Host
  to `localhost` and add configuration contract tests
- [x] T186 [US1] Run complete frontend and release gates, record exact before/after evidence in
  `renderer-boot-analysis.md`, and converge active artifacts in `renderer-boot-convergence.md`

## Phase 23: User Story 10 — Agent Access production hardening

**Goal**: Close the remaining local-origin, forwarded-identity, lifecycle-retention and real-browser
quality gaps without widening the read-only agent boundary.

**Independent Test**: Attempt credentialed preflight and refresh from an unrelated localhost port,
send a forged `X-Forwarded-For`, race issuance and revocation, create more than 100 inactive rows
for two users, export a backup, and exercise Agent Access in production Chromium at 320, 390 and
1,440 px in English and Italian. Verify exact-origin isolation, active-cap enforcement, owner-only
retention, no grant material in export, WCAG 2.2 AA, keyboard entry and no bearer after route exit.

- [x] T187 [US10] Remove the permissive localhost CORS default, keep credentialed origins exact,
  make Compose backend-only, disable proxy-header trust in container/native runtimes and add
  measurable configuration and request-identity tests
- [x] T188 [US10] Equalize unknown-account CLI password work, serialize all grant mutations, order
  history by lifecycle transition and prune only the owner's inactive tail in bounded batches
- [x] T189 [US10] Align runtime/static secret and bounds schemas, prove backup exclusion, cross-user
  erasure/restore behavior, concurrent active-cap enforcement and revocation idempotency
- [x] T190 [US10] Add bilingual interrupted-issuance guidance, hide the closed mobile drawer from
  off-screen traversal and add a fresh-build Playwright WCAG 2.2/responsive/lifecycle/secret gate
- [x] T191 [US10] Run focused and complete backend/frontend/distribution gates, record exact evidence
  in the Agent Access analysis/convergence artifacts and leave no test service running

## Phase 24: User Story 1 — Fail-closed local session and distribution boundary

**Goal**: Preserve a small professional login boot while making runtime configuration, credential
bounds, logout truthfulness, API compression and rollout caching fail closed.

**Independent Test**: Reject malformed environment/CORS/API-base/password inputs, fail then retry
an explicit logout without remounting private content, and inspect a hardened production container:
HTML and logo revalidate, fingerprinted CSS/JS are immutable and gzip-compressed, and a private API
response over 1,000 bytes has one no-store policy and no content encoding.

- [x] T192 [US1] Amend constitution, specification, plan and tasks for canonical local runtime
  configuration, truthful session termination, private-response compression and rollout caching
- [x] T193 [US1] Validate environment, JWT, signing-secret, exact CORS, exact renderer API-base and
  bcrypt UTF-8 boundaries; add explicit logout failure/retry with the workspace unmounted
- [x] T194 [US1] Lazy-load the authenticated workspace and layered Bootstrap CSS, compact locale
  namespaces without removing keys and ratchet login plus authenticated-chunk raw/gzip budgets
- [x] T195 [US1] Restrict immutable caching to fingerprinted assets, revalidate HTML/unhashed
  assets, disable dynamic API compression and add static/container header and transfer contracts

## Phase 25: User Story 1 — Replay-detecting browser refresh sessions

**Goal**: Replace the documented 14-day stateless refresh replay window with bounded,
restart-durable, digest-only session families while preserving local and container login flows.

**Independent Test**: Race the same token through two file-backed SQLite sessions, replay the old
token after a normal rotation, log out with an already rotated token, submit a signed pre-migration
token without `sid`, force issue and rotation commit failures, restore and erase one of two users,
and round-trip the migration. Verify one race winner followed by family revocation, cleared invalid
cookies, no raw token/JTI at rest or in backup, an eight-row cap and zero partial persistence.

- [x] T196 [US1] Amend constitution, specification, plan, tasks and data model for required claims,
  bounded digest-only session families, CAS rotation, replay revocation and access-token residual
  lifetime
- [x] T197 [US1] Add the `AuthSession` model and Alembic revision, database-unique account slots,
  bounded issuance, atomic rotation, replay detection and current-or-old-token revocation
- [x] T198 [US1] Integrate login/register/refresh/logout, restore and erasure lifecycle behavior;
  exclude session state from portable archives and close the renderer when a refreshed retry is 401
- [x] T199 [US1] Prove required claims, digest-only storage, sequential and concurrent replay,
  logout with an old token, pre-migration rejection, allocation bounds, cross-user portability,
  migration cascade/round-trip and issue/rotation rollback
- [x] T200 [US1] Run focused and proportional broad gates, record exact evidence in
  `refresh-session-analysis.md`, and converge the active artifacts in
  `refresh-session-convergence.md`

## Phase 26: User Story 1 — Live access-family authority

**Goal**: Remove residual access-bearer authority after committed family revocation, make client
identity transitions deterministic and fail every Node-backed entry point before work on an
unsupported runtime without adding token persistence or a schema migration.

**Independent Test**: Bind access and refresh JWTs to one stable `sid`, rotate and race refreshes,
log out one or two presented families, inject a logout commit failure, restore and erase one of two
users, overlap login/register/refresh calls, retry a terminal protected `401`, send every auth
mutation with missing Origin and hostile Fetch Metadata, and run preflight on Node 24.18 and an
older 24.x runtime. Verify live-family rejection after each committed lifecycle event, atomic
rollback plus cookie clearing and in-memory bearer retry, last-started-wins identity, native caller
compatibility and fail-fast coverage for every npm entry point.

- [x] T201 [US1] Amend constitution, specification, plan, tasks, data model, OpenAPI and privacy
  guidance for mandatory access `sid`, live family authority, the in-flight request boundary and
  no new access-token persistence or schema revision
- [x] T202 [US1] Issue and rotate access/refresh pairs under one stable family, require the live
  indexed family lookup on every protected request and revoke cookie/bearer families atomically
- [x] T203 [US1] Clear refresh cookies and preserve an in-memory bearer retry after logout commit
  failure; make account transitions last-started-wins and harden missing-Origin browser mutations
  with Fetch Metadata without rejecting native callers that omit both headers
- [x] T204 [US1] Enforce `>=24.18.0 <25` with npm engine strictness, an executable version checker,
  lifecycle hooks for every Node/Vite/Playwright/Tauri entry point and an exhaustive manifest test
- [x] T205 [US1] Run focused and complete backend/frontend/Rust/static gates, record exact evidence
  in `access-session-analysis.md`, and converge every active artifact in
  `access-session-convergence.md`

## Phase 27: User Story 5 — Crash-recoverable vault lifecycle

**Goal**: Make reset, restore and complete erasure restart-safe, purpose-isolated and durably
cleanable while preserving shared content-addressed files and responsive desktop health probes.

**Independent Test**: Kill restore after its first file publication, retry the same archive, lose
the archive and erase instead, bind the published file from another account before rollback, race
login with reset, log out an erasure recovery session, corrupt/torn-write the journal, and block a
writer while probing health. Verify deterministic convergence, no unrelated file deletion, no
normal authority while pending, reauthentication-only recovery and non-blocking liveness/readiness.

- [x] T206 [US5] Amend constitution, specification, plan and tasks for four-state lifecycle,
  purpose-bound recovery, durable journal ownership, cleanup sanitation and measurable crash tests
- [x] T207 [US5] Add the constrained indexed `User` lifecycle/fingerprint fields and Alembic
  migration with conservative backfill, pending-state downgrade refusal and migration tests
- [x] T208 [US5] Serialize lifecycle transitions with session issuance, reject normal and
  automation authority while pending, add maintenance-only password reauthentication, invalidate
  erasure sentinels on logout and perform reset/erasure final session sweeps
- [x] T209 [US5] Add the writer-priority activity gate, one maintenance mutex, cancellation-safe
  managed worker state, static root response, pure liveness, non-blocking readiness and ordered
  lifespan shutdown tests
- [x] T210 [US5] Add redundant checksummed monotonic restore journals, owner-scoped staging,
  same-fingerprint retry, lost-archive erasure, durable directory metadata and Windows write-through
  replacement plus managed startup temporary cleanup
- [x] T211 [US5] Derive exact canonical restore paths, reject non-canonical UUID identities,
  preserve newly shared references, revoke restored authority, disable schedules and sanitize
  database/file remnants before clearing failed-restore state
- [x] T212 [US5] Cover journal corruption/torn writes, process loss, SQLite/WAL privacy, shared-file
  rollback, auth races/logout recovery, activity contention, storage faults and bounded upload and
  archive resources with focused backend tests
- [x] T213 [US5] Update data model, OpenAPI, architecture and privacy guidance with lifecycle state,
  recovery response, journal, resource ceilings and restored-schedule semantics
- [x] T214 [US5] Run complete Ruff, type, backend, migration and Node-preflight gates and record the
  exact pass/skip/failure counts without weakening unrelated checks
- [x] T215 [US5] Record cross-artifact analysis in `vault-lifecycle-analysis.md`, converge remaining
  gaps in `vault-lifecycle-convergence.md`, rerun affected gates and leave no active test service

## Phase 28: Production-boundary cancellation and containment follow-up

**Goal**: Close implementation gaps already governed by the desktop lifecycle, accessibility,
live-session and release-evidence requirements without expanding product scope or persistence.

**Independent Test**: Hold a shared browser refresh open while cancelling one waiting request,
abort a stalled desktop readiness probe, enter recovery and failed-logout shells from focused
private controls, launch the managed runtime under a secret-bearing parent environment, and force
native package smoke failures. Verify prompt caller cancellation without cancelling other waiters,
bounded bootstrap cleanup, deterministic recovery focus, child-process environment minimization and
zero unverified sidecar cleanup path.

- [x] T216 [US1] Make shared browser refresh waiting caller-cancellable and independently bounded;
  preserve one shared rotation for surviving requests and add focused race regressions
- [x] T217 [US1] Make desktop readiness probes abortable across Strict Mode cleanup and stalled
  loopback responses, with focused platform/component tests
- [x] T218 [US1] Restore deterministic keyboard focus when recovery, failed-logout or failed desktop
  boot UI replaces private content, without creating additional tab stops
- [x] T219 [US4] Remove desktop, vault, automation and host credential variables from the managed
  model child environment while retaining its launch-scoped llama API key and required runtime
  environment
- [x] T220 [US1] Require Windows, macOS and Linux package smoke failure paths to wait for sidecar
  disappearance, then run focused frontend/backend/release/Rust and bundle gates and record exact
  analysis and convergence evidence
- [x] T221 [US1] Restrict data-derived external navigation to HTTPS or validated mail addresses and
  narrow the native opener capability to the same schemes so imported links cannot open HTTP
  loopback services
- [x] T222 [US3] Make Job-Room provider transport ignore ambient proxy variables, reject requests
  outside its exact HTTPS origin and refuse redirects before any second network hop
- [x] T223 [US1] Bound every intermediate release artifact to fourteen days and ordinary CI
  evidence to seven days, with a workflow contract that prevents future default retention

## Phase 29: Renderer CSS delivery boundary

**Goal**: Prevent unauthenticated lifecycle surfaces from downloading authenticated workspace CSS
while preserving the established workspace cascade, accessibility media and responsive behavior.

**Independent Test**: Build under supported Node, inspect the HTML-linked and lazy workspace CSS
assets, then exercise login and the authenticated shell in real Chromium. Verify one small initial
sheet contains login/recovery/boot but no workspace or Bootstrap sentinels, one lazy sheet contains
the complete workspace graph in order, exact raw/gzip budgets pass and responsive/accessibility
contracts remain present.

- [x] T224 [US1] Split the renderer CSS and icon delivery graph at `AuthenticatedWorkspace`, add
  executable initial/lazy selector, cascade, media and byte-budget contracts, run complete frontend
  and pertinent real-browser gates, and record exact before/after evidence in
  `renderer-css-boundary-analysis.md` and `renderer-css-boundary-convergence.md`

## Phase 30: Bounded transport, runtime and content-addressed persistence

**Goal**: Keep hostile or concurrent local/remote inputs bounded before parsing, preserve process
liveness, continuously attest the managed model runtime and make file/database ownership converge
without replacement, orphaning or destructive loser cleanup.

**Independent Test**: Stream an oversized body without `Content-Length`, hold source and photo
parsing while probing liveness, return compressed/oversized/malformed provider and inference bodies,
tamper runtime inventory/model bytes, cancel each install/start phase, and race identical/conflicting
source/photo/artifact writers through real file-backed SQLite connections. Verify early bounded
failure, responsive health, no expanded network request, no unverified process, exactly one byte
publisher, correct per-profile rows and zero temporary/private residue.

- [x] T225 [US1] Extend specification, plan and tasks for pre-parser request ceilings, parser
  offload, strict provider/inference envelopes, continuous runtime inventory and create-if-absent
  content ownership without adding cloud, telemetry or schema scope
- [x] T226 [US3] Bound and validate provider requests/responses plus Job-Room single-flight session,
  CSRF cleanup, exact-origin paths and health timeouts; make local inference transport identity-only,
  size-bounded and strict about model, usage and response contracts
- [x] T227 [US4] Harden managed runtime redirects, timeouts, archive/inventory verification, disk
  preflight, child environment/process ownership, cancellation, shutdown ordering and crash restart
  bounds; verify one checksum-pinned real runtime archive
- [x] T228 [US1] Enforce ASGI request-body and startup configuration ceilings, bound PDF/DOCX/text
  expansion, make photo decoding request-local, split source parsing from persistence and offload
  CPU-heavy source/photo work while liveness remains responsive
- [x] T229 [US5] Make source, photo and resume artifact publication/deletion create-if-absent,
  transaction-owned, race-safe and durably recoverable with shared-reference preservation
- [x] T230 [US5] Add repeated thread and two-connection SQLite races, upload/decompression faults,
  chunked-body, provider/inference stream, runtime tamper/cancel and liveness regressions
- [x] T231 [US1] Run complete backend, frontend, distribution and applicable browser gates; record
  exact evidence and residual environmental limits in production-hardening analysis/convergence
