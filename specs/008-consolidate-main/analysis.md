# Independent consistency analysis: Consolidate all work into main

Date: 2026-10-17. Status: baseline integrated; follow-up locally verified.
Constitution 2.0.1 remains unchanged.

The primary agent reviewed history, protection and validation evidence. Separate
backend, frontend and supply-chain reviewers assessed disjoint implementation
areas, then reviewed cross-cutting security and artifact consistency. This is an
assessment of evidence, not approval to skip outstanding checks or publish.

## Traceability

All twelve functional requirements and ten success criteria have task coverage;
all twenty-six tasks map to requirements. Coverage means an implementation/verification
task exists, rather than asserting every outcome has already passed.

| Item | Implementation / evidence tasks | Current evidence |
| --- | --- | --- |
| FR-001 | T001 | Refactor commit, inventory, verified recovery bundle |
| FR-002 | T002, T003, T009, T012 | Branch equivalence ledger, independent reviews and structural remediation |
| FR-003 | T004, T005, T012, T013 | Current-auth provider API/UI; consent, bounded transport, independently checked credential mask and proposal authority retained |
| FR-004 | T004, T021 | Fresh migration, provider-only version-9 portability, strict commit identity and rollback/isolation tests |
| FR-005 | T006, T007, T014–T021 | Initial dependency/image/action gates passed; automated follow-up locks, provenance, no-telemetry preservation and deterministic ORM fixture verification |
| FR-006 | T001, T010, T018 | PRs #112/#115 merged through the standard API; signed main 1b897f0 equals the tested source and baseline ref cleanup is complete. Follow-up publication requires new checks |
| FR-007 | T008, T009, T012 | Exact passed, failed, interrupted, pending and skipped checks in validation.md |
| FR-008 | T011 | OS-temporary test evidence, private-data boundaries and final cleanup inventory |
| FR-009 | T022, T026 | Real Uvicorn Config/ASGI trace in both startup orders, content-free idempotent server/access events and copied exception-cache protection; ten focused passes and independent review |
| FR-010 | T024, T026 | Acknowledged create/update/delete/toggle/import state applied before refresh; actual returned imported rows retained; focused red/green and complete frontend checks pass |
| FR-011 | T025, T026 | Contained metadata/digest/length check before photo reuse; meaningful red/green, rollback/API/concurrency controls and independent review |
| FR-012 | T023, T026 | Invalid UTF-8/deflate/LZMA mapped at the archive boundary; parser, inspect and restore regressions plus all 222 portability tests pass |
| SC-001 | T001, T003, T009 | Original tips and content decisions recorded; eight complete verified recovery bundles preserve baseline history |
| SC-002 | T004, T005, T008, T012, T024 | Follow-up Windows backend 2,965 passes/17 skips/82.06% combined coverage, four performance tests, frontend 698 tests, eight browser/API groups, Rust 28 tests and fresh migration roundtrip pass |
| SC-003 | T004, T008, T021 | Fresh migration roundtrip passed; strict archive, provider-only and timestamp identity cases covered |
| SC-004 | T006–T009, T012, T018–T020 | Initial source/image/native/remote gates passed; exact follow-up audit/privacy/test results remain required |
| SC-005 | T010 | Signed baseline main, exact-tree verification and branch cleanup complete; follow-up work remains isolated pending new protected integration |
| SC-006 | T004, T005, T011 | No personal fixtures; deterministic manual/provider/backup flows work without inference |
| SC-007 | T022, T026 | Ten passing real-configuration/cache/privacy regressions retain only safe diagnostics; no private test values printed |
| SC-008 | T024, T026 | Create/update/delete/toggle/import refresh failures, retries, write errors, cancellation and UI single-flight covered |
| SC-009 | T025, T026 | Five damaged-storage cases reject without selection/revision changes; healthy duplicate is idempotent and real API returns 422 |
| SC-010 | T023, T026 | Three malformed formats across parser/inspect/restore return bounded validation errors and preserve ready lifecycle, records and session |

The five specified outcomes and nine numbered plan decisions are represented.
All eight constitution principles remain applicable: local canonical ownership,
validated local/authorized-agent analysis, truthful proposals, recoverable durable
storage, explicit module boundaries, measurable delivery, secure distribution and
accessible interfaces. There is no constitution amendment or new waiver.

## Findings and disposition

A1–A15 are historical integration findings, completed on signed baseline main
except A6's explicit future release qualification obligations. Their original
discovery remains recorded without treating intermediate pending checks as current
failures. A16–A19 describe the owner's subsequent correction cycle.

| ID | Finding | Disposition / task |
| --- | --- | --- |
| A1 | Initial provider service/schema modules exceeded the preferred module size | Resolved by T012: all new provider modules below 300 lines, 186 focused passes, independent AST/JSON/OpenAPI equality; no new exception |
| A2 | Grouped frontend updates initially exceeded the unchanged entry bundle budget | Resolved by actual deferred authentication-only router loading: final entry 266,593 bytes, complete frontend coverage/lint/build pass, budgets unchanged |
| A3 | Old npm CLI E404 results falsely suggested that patched versions were unavailable | Corrected in integration.md and validation.md; fresh OS-cache official registry/install/audit evidence supersedes the availability inference |
| A4 | Initial aggregate and protected checks were pending | Resolved for signed main 1b897f0: Windows 2,944 passed/17 skipped/82.03%, Linux 2,950 passed/11 skipped/83.59%; full frontend, eight E2E groups, performance, static/native/migration/audits and protected gates passed. Follow-up evidence is recorded separately |
| A5 | Initial protected-main publication and branch cleanup were pending | T010/T011 completed: PR #115, valid signature, exact reviewed tree, eight verified bundles and main as sole local/remote branch. Disclosed policy-blocked cache deletion was not bypassed |
| A6 | Local shipping-image smoke/scanning and complete native release qualification are not established by source tests | Existing release gates remain mandatory; no production release approval is claimed |
| A7 | Real provider API journey exposed a recoded Unicode secret-mask constant after module extraction; shared expected constants concealed it in focused tests | Resolved by T013: eight ASCII escapes, independent API regression red before/green after, 267 provider/contract passes; all eighteen moved assignments and original string literals match preserved source. Final aggregate/backend/packaging checks remain required |
| A8 | GitGuardian flags a literal synthetic username/password pair in the new provider E2E script | Independent review traces account creation/use exclusively to a fresh OS-temporary loopback vault and cleanup; no service/environment credential is used. T014 generates the password per run, repeats the real journey and retains the exact scanner outcome without exclusions |
| A9 | First real shipping Ollama image scan finds six HIGH vulnerabilities, all with fixes | T015 upgrades Go to 1.27.2, x/net to 0.60.0 and Ubuntu OpenSSL/libssl to the patched baseline; no scanner weakening or ignore file. Initial shipping build and runtime smoke passed, so the remaining failure is specifically the vulnerability gate |
| A10 | Native installer preflight rejects four Rust/npm Tauri version mismatches introduced by the frontend update | T016 aligns the core minor and exact plugin versions per official requirements, with an accurate compiler baseline and renewed lock/notices/native evidence; no preflight bypass |
| A11 | Five Agent Access acceptance jobs fail because their clean hosts import the validator without packaging installed | T017 installs the existing hash-locked tooling closure before that import and adds a clean-host/order regression; the passing Windows runner had an incidental preinstalled package |
| A12 | Dependabot created a new two-patch branch while the original PRs were closing, so the deletion inventory changed | The deletion guard stopped safely. T018 preserves its exact tip, assesses API 2.12.2/icons 1.13.2, reproduces notices and affected checks, and includes it in protected publication before final cleanup |
| A13 | The same post-merge automation wave created a nine-update Python branch without regenerated locks | T019 preserves its tip and verifies compatibility, regenerates coherent hash locks/notices and repeats the affected complete backend and protected gates; input-only dependency updates cannot be merged as production-ready |
| A14 | FastAPI 0.143 introduces telemetry controls whose defaults can activate ambient providers and capture query strings or exception messages | T020 disables all instrumentation/auto-configuration explicitly and tests adversarial ambient configuration before accepting the upgrade; no SDK/exporter or telemetry authority is introduced |
| A15 | Final Windows coverage exposed a time-dependent provider commit-identity positive fixture: editing its original row invokes an automatic updated_at change | T021 reconstructs the complete decoded row with archived timestamps, exactly like restore. Production checks remain unchanged. Deterministic red, timestamp negatives, 19 focused tests, final Windows suite and protected main gates pass |
| A16 | Root-only logging misses real Uvicorn handlers and cached exception text; preformatted vendor messages can contain private prose | T022 protects installed handlers and reapplies policy first in lifespan. Uvicorn output is content-free except allowlisted method/status; sealed events survive repeated handlers. Four original and two stronger privacy cases failed before correction; ten final cases and independent review pass |
| A17 | Invalid UTF-8/deflate/LZMA exceptions escape archive validation and can strand restore-pending | T023 normalizes the precise decoder exceptions at the archive boundary. All nine regressions failed before the fix, then passed; 222 portability tests pass and independent review finds no material issue |
| A18 | A failed provider catalog refresh discards a successful mutation acknowledgement | T024 applies server-returned redacted state immediately and distinguishes refresh failure. Includes actual imported rows/counts, stale/cancel/error paths and pending UI controls. Complete frontend passes with independent review |
| A19 | Duplicate photo upload reports success without verifying existing stored content | T025 checks the owned normalized asset and contained digest/length before selection. Six failures and a healthy control reproduced the issue; seven regressions and 23 focused/API/concurrency tests pass, independently reviewed |

Backend independent review also found saved-header cross-origin leakage and
provider-only archive edge cases during implementation. Those were corrected and
verified with API, outgoing-header, legacy, quota, owner-binding and transactional
failure tests before freezing the local backend baseline. Frontend independent
review verified selected-language lazy loading, consent cancellation, stale
operations, actual backup download bytes, keyboard navigation and accessibility.

No unresolved finding authorizes direct cloud inference, expanded agent grants,
an additional writable vault process, silent fallback, weakened path/archive
checks, fabricated security results or bypassing main protection.

## Follow-up verification disposition

The read-only consistency review finds no uncovered requirement, duplicate task,
constitution conflict or additional unbuilt implementation. T001–T021 are complete
baseline work; T022–T025 are implemented and independently reviewed. T026 is now
complete with actual aggregate evidence and artifact reconciliation. Hooks for
all sixteen changed files pass, including global Ruff and mypy for backend/scripts and
frontend lint. All eight browser/API groups and the Rust gates pass; their initial
guards detected Tauri-generated missing final LFs on three schemas. Exact original
bytes were restored and final guards reconcile with zero differences; that
transient formatting event remains recorded. The full Windows backend passes
2,965 tests with 17 skips and 82.06% combined branch-aware coverage; all four
performance skips pass in the separate enabled run. Thirteen remaining skips are
POSIX-only contracts. Fresh upgrade/downgrade/upgrade passes with intact SQLite
integrity and zero foreign-key violations. Final guards find zero differences
among all 1,173 inputs. The assessment finds no remaining implementation gap.
The known partial mypy invocation and test-harness/attestation errors are retained
in validation.md; a completed focused run never substitutes for an unexecuted gate.
This is the pre-publication source assessment. The new PR's mandatory checks,
signed-main exact-tree proof and final branch inventory are recorded separately
in PR metadata and durable private Git recovery evidence; none is claimed early.
