# Daily-driver workflow analysis

Date: 2026-07-22

## Cross-artifact consistency

| Requirement | Implementation boundary | Evidence |
|---|---|---|
| FR-046 private manual capture | `JobService` derives and resolves a per-user manual namespace; request schemas reject extra and oversized input | Unit and authenticated two-user integration tests cover spoofing, idempotency and visibility |
| FR-047 explicit deterministic plan | `backend/search/deterministic_planning.py` reads only direct role/strategy input and preferences; acquisition never calls the LLM and accepts only provenance-bound cache v3 | Planner and acquisition-boundary tests cover zero, `NULL`, CV/normalized-field exclusion, legacy cache rejection and no model call |
| FR-048 concurrent event CAS | `ApplicationService.append_event` calls `_advance_revision` with the resulting stage before appending the event | Two independent SQLite/WAL sessions synchronize at the CAS; one succeeds and one conflicts |
| FR-049 task integrity and board projection | Replay groups typed snapshots by id/revision; board selects only scalar role/event/task projections | Timestamp reordering, regression, conflicting duplicate and SQL-capture tests that reject event/job-snapshot reads |
| FR-050/051 lossless bounded dossier | UUID evidence schema, aggregate/byte limits and one deduplicated v2 evidence catalog plus repeatable React rows | API size/schema/manifest tests and UI retry/resume-change/multi-row/accessibility tests |

## Privacy and migration review

Manual listing content no longer shares a `ScrapedJob` row across users, even when title, company,
URL and an attacker-supplied platform id match. The opaque hash exposes neither the user id nor the
listing fields. Deterministic provider queries contain no CV prose or unconfirmed model-derived
normalization. The manual importer and projection migration are unreleased on this branch; the
manual namespace therefore needs no historical rewrite, while the projection columns retain their
reversible Alembic migration.

## Residual constraints

Application detail intentionally replays append-only task events because it presents full history;
the board intentionally does not. Application list pagination remains offset/limit for compatibility.
These are product boundaries, not release blockers for this slice.
