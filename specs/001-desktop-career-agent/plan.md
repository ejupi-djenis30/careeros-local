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

## Technical Context

**Language/Version**: Python 3.12.13; Rust 1.84+ (current workspace 1.96); JavaScript/JSX
on Node 24.18.0 LTS

**Primary Dependencies**: Tauri 2.11, React 19, Vite 7, FastAPI 0.139, SQLAlchemy 2,
Alembic 1.18, Pydantic 2.13, PyInstaller 6.21, llama.cpp server b9637

**Presentation**: dependency-free React message catalogue with English as the clean-install
default and Italian as an on-device, user-selected alternative; no locale service or egress

**Storage**: SQLite career vault in the operating-system application-data directory;
content-addressed local assets; atomic JSON manifests for managed runtime/model state

**Testing**: pytest, Vitest/Testing Library, Cargo tests, mocked process/download contract
tests, migration round-trips, packaged-sidecar smoke tests, Tauri installer build matrix,
offline AI golden-set evaluator

**Target Platform**: Windows x64/arm64, macOS x64/arm64 and Linux x64/arm64 desktop; browser and Docker
remain contributor-only development modes

**Project Type**: Cross-platform desktop application with a local Python service sidecar
and a managed native model-runtime child process required for AI analysis

**Performance Goals**: warm local API reads p95 below 200 ms for a 10,000-record vault;
desktop shell interactive within 5 seconds after sidecar readiness; compact-model structured
task median below 45 seconds on reference CPU; canvas interactions at 60 fps for 100 blocks;
application readiness calculation below 100 ms for one application with 300 selected facts

**Constraints**: no remote inference or API keys; zero hidden startup egress; installer does
not bundle the 1.83 GB model; all service/model endpoints loopback-only; one active vault
writer; no user-content logging; release builds are native per operating system

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
- **PASS — Release evidence**: the plan includes unit, contract, integration, evaluation,
  supply-chain, packaged-artifact and lifecycle gates.
- **PASS — Deterministic readiness**: the application preflight reads only local owned records,
  publishes every weighted check, omits storage paths and produces canonical exports without AI.
- **PASS — Truthful analysis**: non-AI Vault, portability, document and deterministic readiness
  workflows remain available without a model, while analysis fails closed unless the loopback
  runtime is ready and a content-free schema probe validates structured output.

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

## Delivery Phases

### Phase A — Identity, hygiene and contracts

Rename every product/package identifier, replace all documentation, remove obsolete output
conventions, establish the feature artifacts, and add tests that reject the old repository
name and remote-AI vocabulary in runtime code.

### Phase B — Desktop runtime

Add the frozen backend entry point, desktop environment validation, session-token middleware,
Tauri shell, readiness splash, graceful shutdown, single-instance behavior, app-data paths,
icons and platform packaging scripts. Browser development stays available without weakening
desktop checks.

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

## Complexity Tracking

| Violation | Why Needed During Migration | Required Resolution |
|-----------|-----------------------------|---------------------|
| Python sidecar adds a process boundary | Rewriting the mature persistence, rendering and workflow domain in Rust would destroy verified behavior and delay desktop delivery | Authenticate loopback, own lifecycle in Tauri, contract-test it, and keep transport replaceable |
| `backend/services/llm_service.py` is 1,896 lines | Existing tests and search consumers import this facade directly | Extract runtime policy, task prompts/contracts, normalization, matching and planning; leave a compatibility facade below 300 lines |
| `backend/services/search_service.py` is 2,986 lines | It coordinates an existing stateful pipeline with many tested transitions | Extract acquisition, catalog persistence, normalization, matching and finalization services; facade below 300 lines |
| `backend/services/search/listing_utils.py` is 1,501 lines | Legacy deterministic mappings are broad and provider-sensitive | Split by normalization domain and retain snapshot tests for mappings |
| Model/runtime acquired after installation | Bundling a 1.83 GB model makes downloads and updates unnecessarily large | Explicit consent, exact allowlisted URLs, displayed size/license, atomic SHA-256 verification and full offline operation afterward |
