# Independent consistency analysis: Consolidate all work into main

Date: 2026-10-17. Status: signed baseline integrated; UI source locally verified.
Constitution 2.0.1 remains unchanged.

The primary agent reviewed history, protection and validation evidence. Separate
backend, frontend and supply-chain reviewers assessed disjoint implementation
areas, then reviewed cross-cutting security and artifact consistency. This is an
assessment of evidence, not approval to skip outstanding checks or publish.

## Traceability

All seventeen functional requirements and fifteen success criteria have task coverage;
all thirty-two tasks map to requirements. Coverage means an implementation/verification
task exists, rather than asserting every outcome has already passed.

| Item | Implementation / evidence tasks | Current evidence |
| --- | --- | --- |
| FR-001 | T001 | Refactor commit, inventory, verified recovery bundle |
| FR-002 | T002, T003, T009, T012 | Branch equivalence ledger, independent reviews and structural remediation |
| FR-003 | T004, T005, T012, T013 | Current-auth provider API/UI; consent, bounded transport, independently checked credential mask and proposal authority retained |
| FR-004 | T004, T021 | Fresh migration, provider-only version-9 portability, strict commit identity and rollback/isolation tests |
| FR-005 | T006, T007, T014–T021 | Initial dependency/image/action gates passed; automated follow-up locks, provenance, no-telemetry preservation and deterministic ORM fixture verification |
| FR-006 | T001, T010, T018, T032 | Baseline including PR #116 is signed and exact-tree verified; the new UI head still requires its own protected checks, merge proof and recovery-backed ref cleanup |
| FR-007 | T008, T009, T012 | Exact passed, failed, interrupted, pending and skipped checks in validation.md |
| FR-008 | T011 | OS-temporary test evidence, private-data boundaries and final cleanup inventory |
| FR-009 | T022, T026 | Real Uvicorn Config/ASGI trace in both startup orders, content-free idempotent server/access events and copied exception-cache protection; ten focused passes and independent review |
| FR-010 | T024, T026 | Acknowledged create/update/delete/toggle/import state applied before refresh; actual returned imported rows retained; focused red/green and complete frontend checks pass |
| FR-011 | T025, T026 | Contained metadata/digest/length check before photo reuse; meaningful red/green, rollback/API/concurrency controls and independent review |
| FR-012 | T023, T026 | Invalid UTF-8/deflate/LZMA mapped at the archive boundary; parser, inspect and restore regressions plus all 222 portability tests pass |
| FR-013 | T027, T031, T032 | Actual production React root/boundary privacy probes, fixed-code diagnostics, real entry wiring and ESLint enforcement; independent review passes |
| FR-014 | T028, T032 | Conversation/request/composer ownership, cancellation, retries and explicit context; meaningful red/green regressions and independent review |
| FR-015 | T029, T032 | Shared topmost modal ownership, nested/out-of-order cleanup and native browser focus/inert tests; measured appearance restored, independent review and final aggregate gates pass |
| FR-016 | T030, T032 | Identity/revision reconciliation, cancelled pending detail reads and generation-bound creation forms; independent review and 43 combined application/jobs tests pass |
| FR-017 | T031, T032 | Current filter/page reconciliation for dismiss/undo/reactivation; stale counts, foreign rows, retries and unmount regressions independently reviewed |
| SC-001 | T001, T003, T009 | Original tips and content decisions recorded; eight complete verified recovery bundles preserve baseline history |
| SC-002 | T004, T005, T008, T012, T024, T032 | PR #116 Windows baseline: backend 2,965 passes/17 skips/82.06% combined coverage, four performance tests, frontend 698 tests, eight browser/API groups, Rust 28 tests and migration roundtrip pass. New UI aggregate gates remain separate |
| SC-003 | T004, T008, T021 | Fresh migration roundtrip passed; strict archive, provider-only and timestamp identity cases covered |
| SC-004 | T006–T009, T012, T018–T020 | Initial source/image/native/remote gates passed; exact follow-up audit/privacy/test results remain required |
| SC-005 | T010, T011, T032 | Signed baseline main, exact-tree verification and branch cleanup complete; new UI work remains isolated pending its own protected integration and final inventory |
| SC-006 | T004, T005, T011 | No personal fixtures; deterministic manual/provider/backup flows work without inference |
| SC-007 | T022, T026 | Ten passing real-configuration/cache/privacy regressions retain only safe diagnostics; no private test values printed |
| SC-008 | T024, T026 | Create/update/delete/toggle/import refresh failures, retries, write errors, cancellation and UI single-flight covered |
| SC-009 | T025, T026 | Five damaged-storage cases reject without selection/revision changes; healthy duplicate is idempotent and real API returns 422 |
| SC-010 | T023, T026 | Three malformed formats across parser/inspect/restore return bounded validation errors and preserve ready lifecycle, records and session |
| SC-011 | T027, T031, T032 | Raw production error channels fail before correction; actual root callbacks and service sites emit fixed codes without inspecting errors or unknown values |
| SC-012 | T028, T032 | Stale A/B responses and newer composer drafts reproduced; 17 focused tests pass, including actual errors, read retries and cancellation |
| SC-013 | T029, T032 | Thirteen lifecycle regressions plus existing consumers pass; native Chromium covers three widths, with zero final portal style/bounds differences |
| SC-014 | T030, T032 | Selection, revision, close-with-pending-read, creation acknowledgement and close/reopen form races fail before correction and pass after it |
| SC-015 | T031, T032 | Cross-query dismiss/undo, duplicate refresh, post-unmount acknowledgements and same-query dismissed rows have meaningful regressions |

The six specified outcomes and ten numbered plan decisions are represented.
All eight constitution principles remain applicable: local canonical ownership,
validated local/authorized-agent analysis, truthful proposals, recoverable durable
storage, explicit module boundaries, measurable delivery, secure distribution and
accessible interfaces. There is no constitution amendment or new waiver.

## Findings and disposition

A1–A15 are historical integration findings, completed on signed baseline main
except A6's explicit future release qualification obligations. Their original
discovery remains recorded without treating intermediate pending checks as current
failures. A16–A19 describe the completed correction cycle integrated as signed
main cdc91c1 through PR #116. A20–A25 track the subsequent UI continuation.

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
| A20 | Renderer logs and React production default callbacks forward raw private errors | T027 extracts a boolean-only boundary, installs all three content-free root callbacks and enforces a single allowlisted diagnostic sink with real ESLint behavior tests; actual production red/green and independent review pass |
| A21 | Coach completions overwrite a newer conversation selection or composer draft | T028 binds reads/sends to active request identity and composer revision, separates acknowledged writes from retryable reads and retains local-model/explicit-context gates; 17 focused tests and independent review pass |
| A22 | Independent modal effects release background/scroll or handle Escape underneath another dialog | T029 centralizes ownership and exact restoration. A measured portal-dependent style difference is corrected by extending one existing selector with unchanged declarations; final native style/bounds comparison, independent visual/code review and 55 focused tests pass |
| A23 | Application acknowledgements or pending detail reads steal selection, regress revisions or reopen closed/newly reopened forms | T030 separates catalog/workspace control and adds identity, revision, cancellation and creation-session guards. Additional independent review found and verified the pending-read and close/reopen cases; 43 combined tests pass |
| A24 | Dismiss/Undo responses mutate rows/counts captured from a previous jobs projection | T031 reconciles through the current query and reloads current membership/order, with bounded local acknowledgement and mounted guards; red/green regressions and independent review pass |
| A25 | The first build exceeds the raw workspace budget by 85 bytes; the second passes raw but exceeds gzip by 51 bytes | T029/T032 retain both failed aggregates. Equivalent modal handling is deduplicated and the route-specific analysis gate uses the existing lazy route boundary. Actual build passes at 17,130 raw/5,775 gzip; final 756-test quality run, seventeen route-network assertions and all eight E2E groups pass with unchanged budgets and synchronous modal isolation |

Backend independent review also found saved-header cross-origin leakage and
provider-only archive edge cases during implementation. Those were corrected and
verified with API, outgoing-header, legacy, quota, owner-binding and transactional
failure tests before freezing the local backend baseline. Frontend independent
review verified selected-language lazy loading, consent cancellation, stale
operations, actual backup download bytes, keyboard navigation and accessibility.

No unresolved finding authorizes direct cloud inference, expanded agent grants,
an additional writable vault process, silent fallback, weakened path/archive
checks, fabricated security results or bypassing main protection.

## Historical post-integration verification disposition

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

## Current UI verification disposition

The read-only UI consistency assessment finds no uncovered requirement,
contradictory authority or duplicate task. T027–T031 cover the five reproduced
UI gaps; T032 already covers final independent, browser, aggregate, protected
integration and cleanup work. The additional portal style finding belongs to
T029, preserving the explicitly required appearance rather than adding a redesign.
No additional implementation task or constitution exception is justified.

T027–T031 have completed focused red/green verification and independent review.
T029 also has passing native browser behavior, measured appearance preservation
and eight actual rendered-DOM equivalence cases for the focused analysis view.
Both earlier complete frontend suites pass 756 tests but fail distinct raw/gzip
budget checks. Independently reviewed shared-module deduplication and lazy
route-boundary corrections now pass the actual unchanged build budgets.
T029's renewed focused/native checks pass, as do final full quality, route-loading
and all eight E2E groups. The E2E wrapper's immediate resource guard failed for
one transient descendant; later read-only process/TCP/vault and source guards
are clear without a kill or rerun. The original failure and identity limits are
retained. All applicable hooks pass with zero changes across 1,346 inputs.
T032 is complete as final source verification and integration hand-off.
The new protected integration and recovery-backed
cleanup remain mandatory, with actual execution recorded in the new PR/recovery
ledger; no source checkbox establishes FR-006, FR-008 or SC-005 early.
Backend, native, dependency and
migration inputs are unchanged; their signed baseline evidence remains distinct
from the affected-contract and protected checks required for this UI cycle.
