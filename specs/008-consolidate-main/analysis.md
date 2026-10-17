# Independent consistency analysis: Consolidate all work into main

Date: 2026-10-17. Status: implementation and final verification in progress.
Constitution 2.0.1 remains unchanged.

The primary agent reviewed history, protection and validation evidence. Separate
backend, frontend and supply-chain reviewers assessed disjoint implementation
areas, then reviewed cross-cutting security and artifact consistency. This is an
assessment of evidence, not approval to skip outstanding checks or publish.

## Traceability

All eight functional requirements and six success criteria have task coverage;
all twenty tasks map to requirements. Coverage means an implementation/verification
task exists, rather than asserting every outcome has already passed.

| Item | Implementation / evidence tasks | Current evidence |
| --- | --- | --- |
| FR-001 | T001 | Refactor commit, inventory, verified recovery bundle |
| FR-002 | T002, T003, T009, T012 | Branch equivalence ledger, independent reviews and structural remediation |
| FR-003 | T004, T005, T012, T013 | Current-auth provider API/UI; consent, bounded transport, independently checked credential mask and proposal authority retained |
| FR-004 | T004 | Fresh migration, provider-only version-9 portability and rollback/isolation tests |
| FR-005 | T006, T007, T014–T020 | Initial dependency/image/action gates passed; automated follow-up locks, provenance and no-telemetry preservation are being verified |
| FR-006 | T001, T010, T018 | PR #112 merged through the standard API, signed main tree verified identical; automated follow-up and final ref cleanup pending |
| FR-007 | T008, T009, T012 | Exact passed, failed, interrupted, pending and skipped checks in validation.md |
| FR-008 | T011 | OS-temporary test evidence, private-data boundaries and final cleanup inventory |
| SC-001 | T001, T003, T009 | Original tips and content decisions recorded; final bundle still pending |
| SC-002 | T004, T005, T008, T012 | Final frontend, real-browser, local backend and first Linux backend gates passed; final deployment checks pending |
| SC-003 | T004, T008 | Fresh migration roundtrip passed; strict archive and provider-only cases covered |
| SC-004 | T006–T009, T012, T018–T020 | Initial source/image/native/remote gates passed; exact follow-up audit/privacy/test results remain required |
| SC-005 | T010 | No main merge or branch deletion claimed before protection and content checks pass |
| SC-006 | T004, T005, T011 | No personal fixtures; deterministic manual/provider/backup flows work without inference |

The four specified outcomes and eight numbered plan decisions are represented.
All eight constitution principles remain applicable: local canonical ownership,
validated local/authorized-agent analysis, truthful proposals, recoverable durable
storage, explicit module boundaries, measurable delivery, secure distribution and
accessible interfaces. There is no constitution amendment or new waiver.

## Findings and disposition

| ID | Finding | Disposition / task |
| --- | --- | --- |
| A1 | Initial provider service/schema modules exceeded the preferred module size | Resolved by T012: all new provider modules below 300 lines, 186 focused passes, independent AST/JSON/OpenAPI equality; no new exception |
| A2 | Grouped frontend updates initially exceeded the unchanged entry bundle budget | Resolved by actual deferred authentication-only router loading: final entry 266,593 bytes, complete frontend coverage/lint/build pass, budgets unchanged |
| A3 | Old npm CLI E404 results falsely suggested that patched versions were unavailable | Corrected in integration.md and validation.md; fresh OS-cache official registry/install/audit evidence supersedes the availability inference |
| A4 | Final protected remote checks remain in progress | Final local backend: 2,940 passed/17 skipped/82.03%; first Linux CI backend: 2,946 passed/11 skipped/83.59%. Eight E2E groups, 686 frontend tests, four performance gates, static/native/migration/audits passed. New-head package/container/bootstrap checks remain mandatory; exact wrapper/cleanup failures are retained |
| A5 | Protected-main publication and branch cleanup have not yet occurred | T010/T011 remain open until real checks, recovery preservation and content verification permit completion |
| A6 | Local shipping-image smoke/scanning and complete native release qualification are not established by source tests | Existing release gates remain mandatory; no production release approval is claimed |
| A7 | Real provider API journey exposed a recoded Unicode secret-mask constant after module extraction; shared expected constants concealed it in focused tests | Resolved by T013: eight ASCII escapes, independent API regression red before/green after, 267 provider/contract passes; all eighteen moved assignments and original string literals match preserved source. Final aggregate/backend/packaging checks remain required |
| A8 | GitGuardian flags a literal synthetic username/password pair in the new provider E2E script | Independent review traces account creation/use exclusively to a fresh OS-temporary loopback vault and cleanup; no service/environment credential is used. T014 generates the password per run, repeats the real journey and retains the exact scanner outcome without exclusions |
| A9 | First real shipping Ollama image scan finds six HIGH vulnerabilities, all with fixes | T015 upgrades Go to 1.27.2, x/net to 0.60.0 and Ubuntu OpenSSL/libssl to the patched baseline; no scanner weakening or ignore file. Initial shipping build and runtime smoke passed, so the remaining failure is specifically the vulnerability gate |
| A10 | Native installer preflight rejects four Rust/npm Tauri version mismatches introduced by the frontend update | T016 aligns the core minor and exact plugin versions per official requirements, with an accurate compiler baseline and renewed lock/notices/native evidence; no preflight bypass |
| A11 | Five Agent Access acceptance jobs fail because their clean hosts import the validator without packaging installed | T017 installs the existing hash-locked tooling closure before that import and adds a clean-host/order regression; the passing Windows runner had an incidental preinstalled package |
| A12 | Dependabot created a new two-patch branch while the original PRs were closing, so the deletion inventory changed | The deletion guard stopped safely. T018 preserves its exact tip, assesses API 2.12.2/icons 1.13.2, reproduces notices and affected checks, and includes it in protected publication before final cleanup |
| A13 | The same post-merge automation wave created a nine-update Python branch without regenerated locks | T019 preserves its tip and verifies compatibility, regenerates coherent hash locks/notices and repeats the affected complete backend and protected gates; input-only dependency updates cannot be merged as production-ready |
| A14 | FastAPI 0.143 introduces telemetry controls whose defaults can activate ambient providers and capture query strings or exception messages | T020 disables all instrumentation/auto-configuration explicitly and tests adversarial ambient configuration before accepting the upgrade; no SDK/exporter or telemetry authority is introduced |

Backend independent review also found saved-header cross-origin leakage and
provider-only archive edge cases during implementation. Those were corrected and
verified with API, outgoing-header, legacy, quota, owner-binding and transactional
failure tests before freezing the local backend baseline. Frontend independent
review verified selected-language lazy loading, consent cancellation, stale
operations, actual backup download bytes, keyboard navigation and accessibility.

No unresolved finding authorizes direct cloud inference, expanded agent grants,
an additional writable vault process, silent fallback, weakened path/archive
checks, fabricated security results or bypassing main protection.
