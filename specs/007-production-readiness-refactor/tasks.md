# Tasks: Production Readiness Refactor

## Phase 1: Baseline and intent

- [x] T001 Review constitution, inspect clean worktree and audit backend, UI/native,
  release infrastructure and temporary files (FR-007, FR-008).
- [x] T002 Write specification and plan before production code (FR-001–FR-008).

## Phase 2: Independent implementation slices

- [x] T003 [P] Add delayed resume operation regressions and session/request guards,
  preserving edits within the current draft (FR-001, FR-002; US1).
- [x] T004 [P] Remove dead AI duplication and unused imports, retaining legacy
  exports/patch contracts; run AI regressions (FR-003; US2).
- [x] T005 [P] Consolidate browser backup download onto shared utility and verify
  backup export tests (FR-004; US2).
- [x] T006 [P] Add desktop-wrapper command/preflight tests, require installed CLI
  and targets, enforce locked builds (FR-005; US3).
- [x] T007 [P] Align local lint/type hooks with CI and remove implicit dependency
  installation; cover hook contract (FR-006; US3).
- [x] T008 [P] Ignore generated tooling caches and remove only verified disposable
  artifacts if any exist (FR-007; US4).
- [x] T015 Add extras/malformed-record notice regressions, fix the strict parser,
  canonicalize lock bytes and regenerate the complete verified inventory
  (FR-010; SC-007).

## Phase 3: Verification and review

- [x] T013 [P] Apply verified Python dependency security fixes, regenerate hash
  locks/notices and audit the final environment (FR-009; SC-006).
- [x] T014 [P] Evaluate frontend security fixes, apply compatible installable fixes
  if available, and audit licenses/security (FR-009; SC-006). No supported fix was
  installable; the final full audit remains a release blocker (11 dev findings).
- [x] T009 Run focused regressions, then full backend/static/frontend/native gates
  and temporary-database migration roundtrip (FR-008; SC-001–SC-005).
- [x] T010 Independently review implementation and correct actionable findings
  (FR-008).
- [x] T011 Analyze specification/plan/task consistency and converge implementation
  against acceptance scenarios (FR-001–FR-010; SC-001–SC-007).
- [x] T012 Record exact validation results, release limitations and cleanup inventory
  in the feature evidence; update contributor guidance if entry points change
  (FR-005–FR-010; SC-006, SC-007; US4).

## Phase 4: Convergence

- [ ] T016 HIGH: Apply compatible official fixes for the 11 remaining development
  dependency findings when published, obtain a passing complete npm audit, and
  rerun affected regression/license/build gates before release per FR-009,
  SC-006 and Constitution VII (partial). Current official fixed versions are
  unavailable; see validation.md. Do not suppress or weaken the full scan.
- [ ] T017 HIGH: Qualify the desktop release artifacts through the existing release
  workflows on supported Windows/macOS/Linux systems: clean install, launch,
  restart, supported upgrade, artifact smoke, checksums, SBOM/provenance and
  applicable image scans/model evaluations. Sign where credentials are available
  and state signing status truthfully per Constitution I, IV, VII and product
  gates (partial). Source checks and the temporary unsigned Python wheel smoke
  do not establish installer or release acceptance.
