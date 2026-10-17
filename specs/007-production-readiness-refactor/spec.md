# Specification: Production Readiness Refactor

Date: 2026-10-16. Status: implementation. Owner request: refactor the project,
remove temporary material, and prepare it for production.

## Outcomes and acceptance scenarios

### US1: Draft work survives asynchronous navigation

When a user selects another resume or starts a new one while a previous request is
pending, the previous response must not change the selected document, identity,
revision, status, errors, or output. Of two overlapping loads, only the latest may
select a draft. Edits made while saving the same draft must remain intact.
Delayed save/load/action regression tests exercise these outcomes.

### US2: Maintenance reduces accidental coupling

AI capability modules contain only helpers they use. Compatibility imports and
legacy patch paths keep working. Browser backup downloads use the tested shared
download implementation. Existing deterministic, local inference, evidence, and
vault behavior remains unchanged.

### US3: Local development follows production build constraints

The documented desktop build uses installed tools and locked dependencies. Missing
tools or targets fail with actionable setup instructions; build and lint hooks do
not install tools automatically. Local type and lint hooks cover the CI source
scope with the reviewed tool versions.

### US4: Cleanup and readiness claims are evidence based

Only identified disposable files may be removed. No personal vault, user data,
reference directory, source fixture, development infrastructure, or useful build
dependency is deleted. Generated caches stay ignored. A final report records
executed checks and identifies every failed or skipped gate.

## Functional requirements

- FR-001 Bind resume asynchronous completions to the active editor session and
  ensure latest-load wins, including new/duplicate/delete/publish/generate paths.
- FR-002 Preserve newer edits during a save of the same editor session and cover
  cross-draft races with deterministic tests.
- FR-003 Remove proven dead duplicated AI helpers and unused imports while
  preserving compatibility facade exports and monkeypatch forwarding.
- FR-004 Reuse the shared browser download utility for backup export.
- FR-005 Make the desktop wrapper require installed local CLI and Rust target;
  Cargo production builds must enforce the lockfile.
- FR-006 Align pre-commit lint/type scope and tool pins with CI and fail clearly
  when frontend dependencies are missing rather than installing them.
- FR-007 Inventory temporary files before cleanup and ignore generated tooling
  caches, preserving `.agents`, `.specify`, `specs`, and private runtime material.
- FR-008 Execute backend/frontend/native gates and disposable migration roundtrip,
  independently review the change, and record readiness limits truthfully.
- FR-009 Remediate installable dependency security fixes in Python/frontend locks,
  preserve reviewed source/license constraints, and rerun vulnerability and regression
  gates. Document unresolved advisories instead of suppressing them.
- FR-010 Include every locked Python distribution in the shipped license inventory,
  including requirements with extras such as `httpx[http2]` and `PyJWT[crypto]`.
  Keep lock bytes canonical across checkouts, reject malformed package records,
  and generate the notices through the pinned toolchain with regression coverage.

## Success criteria

- SC-001 Regression tests prove stale requests cannot replace a different resume.
- SC-002 Existing AI and download contracts remain passing after deduplication.
- SC-003 Captured build/hook commands contain no implicit provisioning and production
  builds require the Cargo lockfile.
- SC-004 No temporary output or personal content is added to tracked source.
- SC-005 All required gates have an explicit executed/pass/fail/skip record.
- SC-006 Dependency audits pass, or the evidence identifies exact remaining release
  blockers and why a verified fix could not be applied.
- SC-007 The notice inventory includes both extra-qualified distributions and
  verifies the exact canonical lock bytes and complete license material.

## Boundaries

Constitution 2.0.1 remains unchanged. No schema change, new inference provider,
remote client, authority, release, commit, push, or publication is requested.
Installer signing, supported-OS installation, model-hardware evaluation, and
artifact provenance require their existing release workflows and cannot be
inferred from source tests on one workstation.
