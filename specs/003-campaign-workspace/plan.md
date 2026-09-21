# Implementation plan

## Constitution check

- Local canonical ownership: pass; one explicit ZIP, no cloud client.
- Grounding: pass; original fields/evidence preserved, unknowns not inferred.
- Portability/recovery: requires archive v8 and deletion integration before release.
- Boundaries: parser, importer, API and UI are separate; route handlers remain thin.
- Production evidence: synthetic tests plus disposable-vault real-count validation.
- Safety/accessibility: credentials excluded; inert downloads; keyboard-operable preview.

## Architecture slices

### Slice A — Safe archive and workbook preview

Create `backend/campaigns/` with small modules:

- `archive_policy.py`: canonical path and ZIP structural validation;
- `xlsx_reader.py`: standard-library workbook parsing;
- `vacancy_parser.py`: deterministic dossier-only parsing;
- `preview.py`: reconciliation, fingerprint and bounded preview DTO;
- `schemas.py`: Pydantic request/response types and enums.

No writes in this slice. Add synthetic parser/security/preview tests first.

### Slice B — Persistence and atomic import

- Add the three SQLAlchemy models in `backend/campaigns/models.py` and registry exports.
- Add Alembic revision after `b3c4d5e6f7a9` with constraints/indexes and a data-safe downgrade.
- Extend asset publication for `campaign_document`.
- Implement `backend/campaigns/service.py` orchestration and focused helpers for job/application,
  source-document and artifact creation.
- Import under the authenticated user in one database transaction with the existing publication
  journal/recovery discipline. Same fingerprint returns the existing summary.

### Slice C — API and desktop selection

- `backend/api/routes/campaigns.py`: list/detail, multipart preview/import, application context and
  artifact download. Limit request bytes before ZIP expansion.
- Register router in `backend/api/api.py`.
- Add native ZIP-selection helper following the existing portability dialog/read pattern and the
  narrowest Tauri capability changes needed. Browser input remains supported.

### Slice D — Applications UI

- `frontend/src/services/campaigns.js` for typed-in-practice API calls.
- Decompose React UI into `CampaignImportPanel`, `CampaignPreview`, `CampaignFilters` and
  `CampaignMaterials`; keep each below 150 lines.
- Integrate search/stage/priority filtering and campaign context into existing Applications views.
- Add English and Italian strings and accessibility tests.

### Slice E — Portability, erasure and recovery

- Bump archive format to 8 and include campaign tables in export, inspection, restore and tests.
- Extend empty-vault assertions, reset, erasure/account deletion and shared-asset retention checks.
- Validate migration up/down/up, import idempotence and crash-safe publication cleanup.

### Slice F — Migration utility and real validation

- Add `scripts/build_campaign_archive.py` that accepts a campaign root and output path, includes
  only the FR-002 allowlist, rejects unsafe/oversized input and writes deterministic ZIP metadata.
- Add a read-only validation command/test helper that emits aggregate counts and member digests.
- Build the real local archive outside the repository source tree, import into a disposable vault,
  verify the release counts, re-import, export/inspect/restore, and erase.

## API and compatibility strategy

- API additions are additive under `/api/v1/campaigns`.
- Portable archive current version becomes 8 while versions 1–7 remain inspectable/restorable.
- Existing campaign-null application payloads remain valid.
- No new runtime network access or model dependency.

## Test strategy

1. Unit: ZIP policy, XLSX cells/dates, fingerprint stability, reconciliation, vacancy parsing,
   status mapping, credential omission.
2. Contract: auth/ownership, multipart limits, no-write preview, stale fingerprint, idempotence,
   download headers and traversal denial.
3. Integration: migration, transaction rollback, event/task creation, source candidates, assets,
   portability v8, restore, reset/erasure and shared bytes.
4. Frontend: import preview/confirm, error states, filters, campaign detail/material download and
   EN/IT rendering.
5. Full gates: Ruff, Mypy, Pytest, npm test/lint/build, cargo fmt/clippy/test and migration cycle.

## Implementation-agent protocol

Gemini implements in a single Antigravity conversation using `gemini-3.8-flash-high` and
`--mode accept-edits`. It must:

1. read `AGENTS.md`, Constitution 2.0.1 and every file in this feature directory;
2. inspect current patterns before editing;
3. implement dependency-ordered tasks with targeted tests;
4. never commit, push, modify source campaign files, log private content or bypass permissions;
5. report changed files, tests run and unresolved risks.

Codex then reviews every diff, executes all release gates and sends precise failures back to the
same conversation until convergence. Codex, not the implementation agent, records final validation
and marks the objective complete.
