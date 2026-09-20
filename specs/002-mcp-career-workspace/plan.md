# Implementation Plan: MCP Career Workspace and Template Studio

**Branch**: `codex/002-mcp-career-workspace` | **Date**: 2026-09-13 | **Spec**: [spec.md](spec.md)
**Input**: specs/002-mcp-career-workspace/spec.md

## Summary

Keep the native application as owner of the vault and use a stdio MCP bridge to its authenticated
loopback API. External clients receive scoped context for owner-created work and submit strictly
validated proposals. The renderer performs review/acceptance; existing resume and application
services own mutations and publication. Add versioned template presets and complete packet
materials while preserving existing immutable artifacts.

## Technical Context

**Language/Version**: Python 3.12/3.13 (.venv 3.12.13), React 19 JSX, Node >=24.18 <25, Rust/Tauri 2.
**Primary Dependencies**: Existing FastAPI, SQLAlchemy, Alembic, Pydantic 2, mcp 1.28.1, httpx,
reportlab, python-docx, Pillow, pypdf; React/Vitest/Playwright. No new remote-AI dependencies.
**Storage**: SQLite and contained local files; Alembic for new tables/columns.
**Testing**: pytest, ruff, mypy, Vitest, ESLint, Vite budgets, Playwright, cargo fmt/clippy/test.
**Target Platform**: Native Windows/macOS/Linux, available host Windows ARM64.
**Project Type**: Native desktop with local API and separately installed stdio agent CLI.
**Performance Goals**: Bounded pages <=50 requests; context <=64 KiB, result <=256 KiB; no unbounded
poll loops or LLM work in the request handler. Rendering follows existing bounded artifact limits.
**Constraints**: No private data in fixtures/logs; no silent downloads; no second vault writer;
local model endpoints remain unchanged; all new user text localized.
**Scale/Scope**: Five independently verified user journeys, nine presets, three layouts,
three external work kinds (discover, analyze, materials), existing single-user account boundaries.

## Constitution Check

Pre-research and post-design checks PASS against constitution 2.0.0:
- Native lifecycle and lock stay authoritative. stdio bridge forwards to desktop-owned services.
- No cloud provider SDK/API keys or remote inference URL are introduced. External processing
  takes place in the separately authorized client.
- Old scopes retain semantics; context/proposals require new explicit scopes and disclosure.
- Evidence, schema, stale-input and grant checks precede proposal writes and desktop acceptance.
- New schema is migrated, portable and integrated into reset/restore/erasure.
- UI, transport and logs preserve privacy; ATS and visual output QA remain required.
- Specifications precede implementation. Spark/Antigravity performed the initial delegated slices; after
  their quota exhaustion, the owner's explicit follow-up authorized direct coordinator/subagent
  implementation while retaining independent review and the same acceptance gates.
- Release gates remain unchanged; this task does not authorize publication.

## Project Structure

### Documentation (this feature)

spec.md, plan.md, research.md, data-model.md, contracts/agent-workspace.md,
contracts/templates-packets.md, quickstart.md, tasks.md, checklists/requirements.md,
analysis.md, convergence.md, validation.md.

### Source Code (repository root)

- backend/agent_work/: new focused schemas/models/context/validation/service/acceptance modules.
- backend/automation/: preserve old facade/runtime; separate desktop_client.py and
  workspace_mcp.py from mcp_server.py dispatch.
- backend/api/routes/agent_work.py: owner-authenticated queue/review actions.
- backend/api/routes/agent_bridge.py: grant-authenticated fixed operations, no owner authority.
- backend/api/: narrow middleware exemption only for exact bridge routes, still enforcing
  loopback/Host/origin/body bounds and its distinct grant authentication.
- backend/resumes/templates.py: immutable declarative presets; template selection metadata
  threaded through draft/canvas/publication/restore/portability.
- backend/resumes/renderers/: implement distinct layouts using existing local renderers.
- backend/applications/: extract dossier orchestration into focused services before extension;
  letter/email/rendering modules reuse immutable storage and manifest facilities.
- backend/career/: selected Markdown/text source import via existing review workflow.
- backend/migrations/versions/: ordered additive migrations.
- frontend/src/features/agent-work/: queue/create/context status/review/accept/reject.
- frontend/src/features/agent-access/: expanded disclosure/scopes and correct open-desktop setup.
- frontend/src/features/resume-studio/: template gallery/filter/preview/content-preserving switch.
- frontend/src/features/applications/: materials request, review/edit, letter/email/packet export.
- tests/backend/{agent_work,automation,resumes,applications,portability,security}/ plus UI tests.

**Structure Decision**: Preserve domain service boundaries; external transport never writes SQL
or arbitrary files directly. Existing read-only AutomationFacade stays under 300 lines. New
production Python modules target <300 lines and React components <150. Do not grow the existing
large ApplicationService; extract dossier concerns with characterization tests first.

## Implementation design

1. Work is explicitly created by the owner from agent workspace or a selected job/application.
   A chosen active grant binds the request. Grant scope additions are context:read and
   proposals:write; old grants do not inherit them.
2. Default MCP CLI stays offline/read-only. --desktop-url selects a stdio HTTP proxy that never
   bootstraps/locks/opens the database itself. It accepts only canonical http loopback URLs with
   explicit port and /api/v1 base, fixed route construction, trust_env=False, no redirects,
   bounded response bodies and deadlines. It reads CAREEROS_MCP_TOKEN only from environment.
3. Bridge request authentication validates live grants and ready vault lifecycle without using
   browser JWT or X-CareerOS-Session as agent credentials. Exempt only the exact bridge namespace
   from the desktop session header; do not weaken normal endpoint/middleware checks. Origin,
   Host, client address, media type and request-size policies remain enforced. No permissive CORS.
4. Work snapshots use confirmed owner facts and explicit selected preferences, excluding contact
   identity/reference material by default. Include stable fact IDs and untrusted-data labels.
   Explicit context grant acknowledges residual career prose disclosure.
5. At submit, verify grant, request binding, expiry/state, body/schema/size, exact input digest,
   all fact/job references, ranges and unsupported claims. Preserve client/model labels as
   self-reported provenance, never local_model_validated attestation. A citation is necessary
   but not proof: deterministic constraints reject foreign evidence, new dates/employers/metrics
   unsupported by cited facts; all generated prose remains review-required.
6. Accept/reject endpoints require owner session and expected revisions. Lock/CAS request and
   all targets including CV and dossier draft revisions within one transaction. Recheck inputs
   AND grant validity; invoke existing domain
   mutations transactionally without hidden intermediate commits. Repeated identical accept
   returns stored receipt. Changed target, revoked authority or conflicting payload fails.
   Existing ResumeDraftService, ApplicationService and BaseRepository methods commit internally;
   a nested savepoint alone is insufficient. Extract flush-only transaction primitives or a
   reviewed unit-of-work seam with characterization tests. Unpublished dossier preparation
   must support a draft CV binding via migration; published dossiers still require real versions.
7. Discovery acceptance reuses manual catalog import and logical application identity. Preserve
   observations and raw source snapshot; no network request is performed by agent ingestion.
   Agent mode does not require local inference. Legacy local matching/coaching still does.
   Always choose the server-owned per-user manual capture namespace for external discoveries;
   never accept agent-selected provider/platform identifiers that could reuse another owner's
   private raw listing in the shared catalog.
8. Template catalog uses three layout identities and nine presets; preserve ats/photo legacy
   kinds as compatibility capabilities rather than expanding them into nine duplicate renderers.
   Persist preset ID/version/locale/layout in draft/version snapshots via additive schema.
   Switching applies layout style only, preserves content, validates photo constraints and makes
   changes reviewable. No dynamic HTML/CSS execution.
9. Packets extend existing revisioned dossier rather than inventing parallel storage. Proposed
   claims map to fact evidence; local identity fills contacts for export. Cover letter PDF/DOCX
   and offline .eml (or explicit email text artifact with attachment checklist) are generated
   locally with no transmission. Manifest verifies all selected files; finalization rejects
   unresolved placeholders, missing attachments and stale profile/job/application/template inputs.
   Enhanced packet schema 3.0 persists actual ZIP bytes with an owned artifact row and atomic
   journal; legacy schemas 1.0/2.0 keep their original reconstruction for historical integrity.
   Database CAS covers the dossier and all publication bindings. Validate the full saved
   publishable content and evaluate readiness against the explicitly selected CV version.
   Resolve uncertain commit outcomes before deleting staged artifacts; post-commit journal
   cleanup cannot roll back a committed publication. Reconcile journals under the vault lock
   and retain them after failed cleanup. Dispatch downloads by event schema, validating schema 3
   artifact identity/manifest instead of falling back to reconstruction when bytes are missing.
10. Selected .md/.txt references go through bounded import with explicit source role; preview
    narrative separately from facts and goals as explicit preference candidates only, following
    contracts/reference-import.md. No recursive arbitrary directory reads or script execution.
    Validate the entire merged preference DTO before editing, explain scalar replacement and
    conflicts, and preserve candidate selection after failure. Bound notes with an omission
    summary. Associate async import/save responses with their request and editor revision so
    older replies cannot discard newer selections or mark later edits as saved.
11. Distribute the stdio bridge with the native backend/launcher, exposing its actual installed
    command in setup. Retain explicit developer CLI setup. Native capability remains narrowly
    scoped to finding the packaged bridge; it never exposes the desktop bearer to MCP.
    Windows GUI PyInstaller binaries have no usable stdio; bundle a separate console-capable
    bridge executable in the same inventoried runtime, rather than pointing MCP at the GUI
    sidecar. The installed bridge resolves the current loopback URL from a bounded, privately
    written local connection descriptor (no tokens), refreshing it after desktop restarts.
    The descriptor and its canonical absolute path reject symlinks/traversal, carry only the
    allowlisted loopback base and version metadata, and use atomic writes. Shutdown invalidates
    it; stale/missing/unreachable descriptors fail closed without direct database fallback.
    Explicit --desktop-url remains supported for development and controlled protocol tests.

## Migration and portability

Create ordered additive migrations after the existing head. Cover empty and prior-schema
upgrades, downgrade and re-upgrade, preserving old grant scope values and published artifact
hashes. Include new owned records in backups with strict schema and relationship validation;
exclude raw tokens/live authority. Restore requests as canceled/inactive, requiring new grants.
Reset/erasure delete owned work and proposals in dependency order; maintenance blocks bridge.
Preserve historic artifact bytes and legacy snapshot compatibility.

## Validation strategy

Run baseline before implementation, then targeted tests per slice including negative security,
concurrency, stale input, replay/idempotency and rollback cases. Real MCP SDK memory/stdio
protocol tests cover discover/list/context/submit and metadata authority. Browser tests traverse
all new UI journeys with fictional data. Render all nine CV presets and letters, inspect PDF text
and DOCX paragraphs/tables, A4/page count and representative page images from each layout.
Full gates: ruff, mypy, pytest tests/backend -q; npm test/lint/build and e2e; cargo fmt,
clippy --all-targets -- -D warnings, cargo test; Alembic upgrade/downgrade/upgrade on temp DB.
Run existing evaluation and portability checks. Record failed/skipped gates exactly.
Add versioned discover/analyze/materials golden fixtures (including unknowns, contradictory
totals, false claims, stale inputs and source injection) and report schema validity, evidence
coverage, unsupported-claim rejection and gate/ranking correctness against expected outcomes.
Never access real data/vault for tests. Temporary files belong in OS temp.
Review findings go to an authorized implementation model or, under the owner's later explicit
authorization, to the coordinating agent; every correction still receives independent review.

## Pre-merge correction plan

The owner-requested final audit on 2026-09-13 reopened five bounded defects before integration:

1. Enforce the catalog's preset/version/locale tuple in the shared resume resolver and exercise
   both direct resolution and write/generate schemas.
2. Treat current local and current accepted-external analysis receipts equivalently when building
   the allowlisted application match snapshot, while retaining exact-value stale checks.
3. Add an explicit disclosure acknowledgement to CLI grant issuance and pass it to the existing
   grant policy; keep omission fail-closed.
4. Move strict duplicate-key/non-finite JSON decoding to a neutral core helper and apply it to the
   portable archive, nested packet restore and packet download verification boundaries.
5. Remove the personal absolute reference path from committed evidence, run targeted regressions,
   repeat every backend/frontend/Rust/migration/packaged-sidecar gate, obtain independent review,
   then commit and fast-forward the authorized feature into local `main`.

## Complexity Tracking

The existing ApplicationService exceeds guidance; dossier extraction is an explicit task,
with compatibility facades below 300 lines where introduced. A second process exists only as an
MCP stdio adapter, justified by the client protocol, without a second writable vault connection.

The convergence review also assessed the few cohesive feature files above the advisory size
targets. `backend/career/reference_parsing.py` keeps one bounded role-aware grammar together;
`backend/portability/workspace.py` keeps the version-7 record graph and strict relationship
validation together; `backend/resumes/templates.py` is predominantly an immutable nine-preset
catalog; and `frontend/src/features/career-profile/SourceImporter.jsx` keeps request/revision
coordination beside the import editor. Their helpers and material/application orchestration were
already extracted into focused modules. Splitting these four remaining units would duplicate
schema/state invariants without creating a stable independent boundary, so T053 records the
completed decomposition follow-up and requires reassessment when another format/schema is added.
