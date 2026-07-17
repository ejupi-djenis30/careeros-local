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
- [X] T013 Create and round-trip-test the AI audit migration in `alembic/versions/` and `tests/backend/integration/test_ai_audit_migration.py`
- [X] T014 Implement redacted AI execution audit recording in `backend/ai/audit.py` and cover content exclusion in `tests/backend/ai/test_audit.py`

**Checkpoint**: Desktop requests can be authenticated, local paths are safe, structured contracts
exist, and content-free AI audit data can migrate without modifying career records.

---

## Phase 3: User Story 1 — Install and own a private workspace (Priority: P1) 🎯 MVP

**Goal**: A clean-machine native application owns its sidecar, vault and shutdown lifecycle.

**Independent Test**: Build the frozen backend and native development app, launch with no Docker or
system Python, create data, restart offline, and confirm zero orphaned child processes.

### Tests for User Story 1

- [X] T015 [P] [US1] Add frozen-entry argument, migration-backup and readiness tests in `tests/desktop/test_backend_entry.py`
- [X] T016 [P] [US1] Add Rust unit tests for random-port allocation, sidecar arguments, bootstrap redaction and bounded restart in `frontend/src-tauri/src/lifecycle.rs` and `frontend/src-tauri/src/commands.rs`
- [X] T017 [P] [US1] Add frontend bootstrap/client session-header tests in `frontend/src/platform/desktop.test.js` and `frontend/src/lib/client.desktop.test.js`
- [X] T018 [P] [US1] Add packaged-process lifecycle acceptance coverage in `tests/desktop/test_packaged_lifecycle.py`

### Implementation for User Story 1

- [X] T019 [US1] Implement frozen backend CLI, environment initialization, migration backup/restore, parent watchdog and clean Uvicorn shutdown in `desktop/backend_main.py`
- [X] T020 [US1] Define reproducible PyInstaller analysis, data files and hidden imports in `desktop/careeros-backend.spec`
- [X] T021 [US1] Implement the verified one-folder resource build flow and optional non-distributed one-file diagnostic in `scripts/build_backend_sidecar.py`
- [X] T022 [US1] Implement Tauri random-port/session creation, single-instance backend spawn, readiness state and shutdown in `frontend/src-tauri/src/lifecycle.rs` and `frontend/src-tauri/src/main.rs`
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

- [ ] T029 [P] [US2] Expand payload-schema, date-consistency and fact-provenance tests in `tests/backend/career/test_payloads.py` and `tests/backend/career/test_service.py`
- [ ] T030 [P] [US2] Add profile completeness and goal milestone interaction tests in `frontend/src/features/career-profile/CareerProfilePage.test.jsx`

### Implementation for User Story 2

- [ ] T031 [US2] Complete typed payload validation for experience, achievements, skills, projects, education, credentials, languages and activities in `backend/career/payloads.py` and `backend/career/schemas.py`
- [ ] T032 [US2] Add deterministic completeness, temporal-conflict and missing-evidence analysis in `backend/career/completeness.py` and `backend/career/service.py`
- [ ] T033 [US2] Extend goal payloads with target constraints, milestones, actions, skill gaps and progress validation in `backend/career/goal_schemas.py` and `backend/career/service.py`
- [ ] T034 [US2] Surface detailed sections, evidence state, completeness and goal progress with keyboard-safe controls in `frontend/src/features/career-profile/`

**Checkpoint**: User Story 2 is independently usable as a detailed local career vault.

---

## Phase 5: User Story 3 — Generate and manually refine truthful resumes (Priority: P1)

**Goal**: Profile facts produce ATS/photo resumes that remain fully editable on a safe canvas.

**Independent Test**: Generate both variants, edit/reorder/resize/hide blocks, undo/redo, save and
restore versions, export PDF/DOCX, and verify evidence, text extraction and overflow behavior.

### Tests for User Story 3

- [ ] T035 [P] [US3] Expand automatic-selection, claim-grounding and template-policy tests in `tests/backend/resumes/test_generator.py` and `tests/backend/resumes/test_claims.py`
- [ ] T036 [P] [US3] Add canvas keyboard, direct-edit, geometry, undo and overflow tests in `frontend/src/features/resume-studio/canvas/ResumeCanvas.test.jsx` and `frontend/src/features/resume-studio/canvas/canvasReducer.test.js`
- [ ] T037 [P] [US3] Add PDF/DOCX text-order, metadata and overflow integration tests in `tests/backend/resumes/test_renderers.py`

### Implementation for User Story 3

- [ ] T038 [US3] Harden deterministic profile/goal-based fact selection and evidence maps in `backend/resumes/generator.py` and `backend/resumes/claim_service.py`
- [ ] T039 [US3] Complete versioned canvas schema, bounded layout validation and ATS/photo invariants in `backend/resumes/canvas_schemas.py`, `backend/resumes/canvas_validation.py`, and `backend/resumes/canvas.py`
- [ ] T040 [US3] Complete direct editing, keyboard movement, reorder, visibility, sizing, zoom, page guides and undo/redo in `frontend/src/features/resume-studio/canvas/`
- [ ] T041 [US3] Harden local PDF/DOCX publishing, photo metadata stripping and pre-export quality gates in `backend/resumes/renderers/`, `backend/resumes/photos.py`, and `backend/resumes/publication_service.py`

**Checkpoint**: User Story 3 independently produces validated, editable career documents.

---

## Phase 6: User Story 4 — Accurate help from small local models (Priority: P2)

**Goal**: A user explicitly installs a compact local model and receives constrained, grounded,
measurably accurate assistance offline.

**Independent Test**: Install the pinned runtime/model, disconnect networking, run all golden task
families on the compact profile, and meet schema, evidence, hallucination and accuracy gates.

### Tests for User Story 4

- [ ] T042 [P] [US4] Add catalog signature, platform selection, hash and unsafe-archive tests in `tests/backend/inference/test_catalog.py` and `tests/backend/inference/test_managed_runtime.py`
- [ ] T043 [P] [US4] Add schema-constrained llama.cpp/Ollama adapter contract tests in `tests/backend/inference/test_structured_adapters.py`
- [ ] T044 [P] [US4] Add BM25 ranking, context-budget and prompt-injection isolation tests in `tests/backend/ai/test_retrieval.py`
- [ ] T045 [P] [US4] Add schema, grounding, semantic validation and single-repair tests in `tests/backend/ai/test_orchestrator.py` and `tests/backend/ai/test_grounding.py`
- [ ] T046 [P] [US4] Add versioned synthetic golden cases and evaluator metric tests in `tests/ai/fixtures/`, `tests/backend/ai/test_evaluation.py`, and `tests/backend/ai/test_golden_contracts.py`
- [ ] T047 [P] [US4] Add model setup/progress/cancellation UI tests in `frontend/src/features/local-model/LocalModelStatus.test.jsx` and `frontend/src/features/local-model/ModelManager.test.jsx`

### Implementation for User Story 4

- [ ] T048 [US4] Generalize the local inference port for JSON Schema, metadata and runtime capabilities in `backend/inference/ports.py` and `backend/providers/llm/base.py`
- [ ] T049 [US4] Implement the authenticated llama.cpp chat/list adapter and schema response format in `backend/inference/llama_cpp.py`
- [ ] T050 [US4] Upgrade the Ollama adapter to the same schema contract and deterministic task options in `backend/inference/ollama.py`
- [ ] T051 [US4] Implement atomic cancellable runtime/model download, safe extraction, verification, process health and bounded restart in `backend/inference/managed_runtime.py`
- [ ] T052 [US4] Expose catalog, status, install, cancel and restart contracts in `backend/api/routes/local_model.py`, `backend/inference/service.py`, and `frontend/src/services/localModel.js`
- [ ] T053 [US4] Implement deterministic bounded evidence ranking in `backend/ai/retrieval.py` and per-claim grounding checks in `backend/ai/grounding.py`
- [ ] T054 [US4] Implement generate-validate-single-repair orchestration and content-free audit integration in `backend/ai/orchestrator.py`
- [ ] T055 [US4] Migrate coach output to constrained claims/citations/confidence while preserving API compatibility in `backend/career/coach.py` and `backend/career/coach_schemas.py`
- [ ] T056 [US4] Apply task schemas and semantic validators to profile normalization, search planning, job normalization, matching, critique and reranking through `backend/services/llm_service.py`
- [ ] T057 [US4] Implement offline fixture validation, live compact-model execution and aggregate reports in `backend/ai/evaluation.py` and `backend/api/routes/ai_evaluations.py`
- [ ] T058 [US4] Replace Ollama command-line instructions with consent, license, size, progress, cancellation and retry UI in `frontend/src/features/local-model/`

**Checkpoint**: User Story 4 passes offline on the pinned compact model and rejects unsupported output.

---

## Phase 7: User Story 5 — Carry, recover and erase the vault (Priority: P2)

**Goal**: Backups survive installation changes and explicit erasure removes only app-managed data.

**Independent Test**: Export a populated vault, restore into a clean desktop installation, compare
counts/hashes, reject a damaged archive without mutation, then erase app data without touching an
unrelated sentinel file.

### Tests for User Story 5

- [ ] T059 [P] [US5] Add desktop app-data backup/restore and interrupted-upgrade tests in `tests/backend/portability/test_desktop_roundtrip.py`
- [ ] T060 [P] [US5] Add managed model/temp erasure and unrelated-file safety tests in `tests/backend/career/test_desktop_deletion.py`

### Implementation for User Story 5

- [ ] T061 [US5] Include AI audit schema, resume assets and manifest compatibility in `backend/portability/archive.py` and `backend/portability/manifest.py`
- [ ] T062 [US5] Make restore transactional under the desktop vault lock with preflight and rollback in `backend/portability/restore.py` and `backend/desktop/lifecycle.py`
- [ ] T063 [US5] Extend explicit deletion to managed model/runtime, sensitive staging and desktop vault paths in `backend/career/deletion.py` and `backend/inference/managed_runtime.py`
- [ ] T064 [US5] Add desktop-native backup destination, restore source and erasure confirmation flows in `frontend/src/features/home/` and `frontend/src/services/portability.js`

**Checkpoint**: User Story 5 proves ownership, recovery and precise local erasure.

---

## Phase 8: Heavy refactor, documentation and production gates

**Purpose**: Remove migration debt, recreate operator/developer guidance and prove release quality.

- [ ] T065 Split AI runtime policy, planning, profile normalization, job normalization, matching and reranking from `backend/services/llm_service.py` into `backend/ai/` and leave a compatibility facade below 300 lines
- [ ] T066 Split acquisition, persistence, normalization, matching and finalization from `backend/services/search_service.py` into `backend/search/` and leave a compatibility facade below 300 lines
- [ ] T067 Split provider-independent mapping domains from `backend/services/search/listing_utils.py` into `backend/search/normalization/` with snapshot parity tests in `tests/backend/search/`
- [ ] T068 [P] Recreate owner, developer, security and architecture documentation in `README.md`, `AGENTS.md`, `SECURITY.md`, `docs/architecture.md`, `docs/development.md`, `docs/privacy.md`, and `docs/releasing.md`
- [ ] T069 [P] Recreate focused backend and frontend contributor guides in `backend/README.md` and `frontend/README.md`
- [ ] T070 Remove all obsolete Markdown/output artifacts and add a repository-hygiene test in `tests/backend/security/test_repository_hygiene.py`
- [ ] T071 Run and fix Python lint, type checks, full pytest, migration round-trips and performance acceptance using `pyproject.toml`, `pyrightconfig.json`, and `tests/backend/`
- [ ] T072 Run and fix frontend lint, full Vitest coverage build, Cargo format/clippy/test and native debug launch using `frontend/package.json` and `frontend/src-tauri/Cargo.toml`
- [ ] T073 Generate and audit Python/npm/Cargo SBOMs, licenses and vulnerabilities in `.github/workflows/ci.yml` and `.github/workflows/desktop-release.yml`
- [ ] T074 Build and smoke-test the Windows installer locally, recording only reproducible commands and truthful results in `specs/001-desktop-career-agent/release-evidence.md`
- [ ] T075 Perform Spec Kit cross-artifact analysis and convergence, append any missing tasks to `specs/001-desktop-career-agent/tasks.md`, and execute them before release
- [ ] T076 Rename the physical workspace directory to `careeros-local`, verify Git remote `ejupi-djenis30/careeros-local`, and rerun a clean status/build check from the new absolute path

---

## Dependencies & Execution Order

### Phase dependencies

```text
Setup -> Foundation -> US1 desktop
                    -> US2 profile
                    -> US3 resume
US2 + Foundation -> US4 AI
US1 + Foundation -> US5 portability
US1..US5 -> Heavy refactor and release gates -> physical folder rename
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

- Total tasks: 76.
- User Story 1: 14 tasks (T015–T028).
- User Story 2: 6 tasks (T029–T034).
- User Story 3: 7 tasks (T035–T041).
- User Story 4: 17 tasks (T042–T058).
- User Story 5: 6 tasks (T059–T064).
- Setup/Foundation/Polish: 26 tasks.
- Every task uses the required checkbox, sequential ID, appropriate story label and exact path.
- Suggested MVP scope: Setup + Foundation + User Story 1.
