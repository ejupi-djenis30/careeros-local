# Plan: Consolidate all work into main

## Constitution check

Reviewed 2.0.1 unchanged: local data/model boundaries, draft proposals, exclusive
desktop vault ownership, explicit consent, evidence/revision validation,
transactional migrations, contained atomic storage and secret-free diagnostics
remain mandatory. Main protections remain in force.

## Integration design

1. Save the validated refactor as a commit. Fetch/prune remote metadata and retain
   a verified complete Git bundle in the OS temporary integration evidence root.
   Record all 12 remote feature/update tips and the local refactor commit.
2. Independently audit three slices: backend/providers/history, frontend/dependency
   compatibility, and images/workflows/main protection. All Git ref mutations are
   coordinated by the primary agent; implementation owners edit disjoint paths.
3. Treat the old workbench as already integrated only with tree/squash evidence.
   Recover the provider capability on current services and contracts, excluding
   obsolete external write/publication tools and constitution regressions. Use a
   fresh migration revision following the current head; never overwrite the old
   branch's colliding b0c1d2e3f4a5 revision.
   Version-9 provider-only archives may have zero candidate profiles when all
   profile-owned records are empty and at least one owned provider exists.
   Preserve strict legacy validation and current relationship/path/user binding;
   restore provider-only data without generating a placeholder career profile.
   Existing provider header secrets must never be implicitly carried to a new
   origin: changing scheme, canonical hostname or effective port requires removing
   or explicitly re-entering the headers. Same-origin masked edits remain safe.
4. Resolve dependency updates by verified published compatibility, preserving
   newer security pins. Regenerate canonical locks/notices with the pinned source
   toolchain. Align image/source versions and hardcoded contract tests together.
   Preserve generated legal text bytes, including upstream trailing whitespace;
   exclude this verified generated asset from whitespace-only hook rewrites while
   retaining the strict generator/digest/license checks.
5. Keep integrated branch provenance in the work branch history and in a manifest.
   Main's signed linear policy and squash-only repository configuration require
   the allowed PR integration path, followed by remote verification and branch
   deletion. Never force-push, change protection, or delete unintegrated refs.
6. Run focused regressions first, then final backend coverage/performance,
   frontend coverage/lint/build/E2E, native/static/license/security checks and
   disposable Alembic roundtrip appropriate to the combined source. Preserve
   previous valid evidence only where source/dependency inputs did not change.
   Load provider-only translations with the provider route and only for the
   selected language. This removes unused provider messages from boot resources;
   prove actual request behavior and keep the existing byte budgets unchanged.
   If updated dependencies increase router boot cost, load the data router only
   when authenticated workspace navigation is actually needed. Login, session
   loading and recovery must retain their independent paths; preserve direct
   links, Tauri hash routing, logout/relogin and the data router's secret-warning
   blocker. Prove that unauthenticated boot does not request the deferred router;
   do not move code into chunks that are still required immediately.
7. Record independent analysis, convergence, exact blockers, final Git state and
   cleanup evidence. Do not present blocked checks as passing or merge eligibility.
8. Complete the decomposition of the recovered provider service and schema graph
   before closing integration. Keep each new production module below 300 lines,
   preserve existing imports and JSON contracts, and verify transaction ownership,
   rollback, revision handling and schema output. Compare moved module constants
   and actual wire values independently as well as function bodies and model
   schemas: a shared expected constant must not conceal encoding corruption.
   This removes the need to rely
   on a new module-size exception or infer an owner-approved waiver.

## Boundaries and size

Existing large-module exceptions from feature 007 remain justified there. Provider
adapters, policy, parsing, registry, transport and UI components remain focused.
Any larger legacy integration surface retains its current responsibility; no new
oversized facade or direct external-agent mutation surface is introduced.

The initial recovery left provider `service.py` at 509 lines and `schemas.py` at
507 lines. Independent analysis identified that a new size exception would need
explicit governance evidence. T012 completed the split instead: service facade
30 lines, catalog 186, mutations 228, imports 138; schema facade 128, validation
119, individual definitions 275 and registry/import documents 144. One
service-owned import transaction remains. Independent review verified identical
moved function bodies, 22 model schemas, five aliases and complete OpenAPI output.
Every new provider production module is below 300 lines. HTTP/DNS transport is
132 lines, the provider client 293 and API transport 283. No new exception is used.
