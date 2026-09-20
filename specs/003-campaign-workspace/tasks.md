# Dependency-ordered tasks

Labels: **G** = Gemini/Antigravity implementation, **C** = Codex planning/review/test owner.

## Phase 0 — Governance and baseline

- [x] C001 **C** Audit tracker, dossiers, artifact roots, current schema and real vault read-only.
- [x] C002 **C** Amend Constitution to 2.0.1 and create feature specification/research/model/plan.
- [x] C003 **C** Record clean baseline gates and existing known failures before implementation.

## Phase 1 — Parser-first tests and preview

- [x] C010 **G** Add fictional XLSX/ZIP fixture builders in tests without personal data.
- [x] C011 **G** Test archive traversal, absolute/UNC/backslash paths, symlinks, encryption,
  duplicates, limits, prefixes, roots and fingerprint determinism.
- [x] C012 **G** Implement `archive_policy.py` to pass C011.
- [x] C013 **G** Test shared/inline strings, booleans/numbers, date styles, missing/duplicate IDs,
  header discovery and credentials-row counting.
- [x] C014 **G** Implement `xlsx_reader.py` to pass C013 without new runtime dependency.
- [x] C015 **G** Test reconciliation and the supported `vacancy.md` patterns.
- [x] C016 **G** Implement `vacancy_parser.py`, schemas and side-effect-free preview service.

## Phase 2 — Persistence/import

- [x] C020 **G** Add campaign models, constraints, registry entries and Alembic migration.
- [x] C021 **G** Extend asset publication journal/storage for `campaign_document` and test recovery.
- [x] C022 **G** Test conservative status/event mapping, active-task creation and closed-task absence.
- [x] C023 **G** Implement atomic campaign import using existing domain services where invariants apply.
- [x] C024 **G** Add root reference SourceDocument import without fact/preference confirmation.
- [x] C025 **G** Test fingerprint idempotence, stale preview, rollback and cross-user isolation.

## Phase 3 — API and UI

- [x] C030 **G** Add authenticated thin campaign routes and request-size enforcement.
- [x] C031 **G** Add contract tests for preview no-write, import, list/detail/context and secure download.
- [x] C032 **G** Add native explicit ZIP selection and browser fallback.
- [x] C033 **G** Add campaign service, import panel/preview, filters and materials components.
- [x] C034 **G** Integrate with Applications page/detail and refresh after import.
- [x] C035 **G** Add EN/IT strings, keyboard/accessibility and frontend tests.

## Phase 4 — Portability and lifecycle

- [x] C040 **G** Bump portable archive to v8 and add campaign export/inspection/restore validation.
- [x] C041 **G** Add reset, erasure, account deletion, empty-vault and shared-asset tests/behavior.
- [x] C042 **G** Add migration up/down/up tests and refuse destructive downgrade with campaign rows.

## Phase 5 — Migration utility and product proof

- [x] C050 **G** Add deterministic allowlist-only `scripts/build_campaign_archive.py` plus tests.
- [x] C051 **G** Add aggregate-only campaign validation helper/documentation.
- [x] C052 **C** Review diff for privacy, transaction, ownership, XSS/path and portability invariants.
- [x] C053 **C** Run targeted and full backend/frontend/Rust gates; return failures to Antigravity.
- [x] C054 **G** Resolve reviewed findings and failing gates in the same Antigravity conversation.
- [x] C055 **C** Build the real archive, import into a disposable vault and verify exact release counts.
- [x] C056 **C** Verify second-import no-op, export/inspect/restore and complete erasure end-to-end.
- [x] C057 **C** Record `analysis.md`, `validation.md`, `convergence.md` and final handoff.

## Completion definition

No phase may be declared complete solely from an implementation-agent statement. Codex must inspect
the diff and observe passing commands. The feature is complete only when C052–C057 are evidenced.
