# Specification analysis: Production Readiness Refactor

Date: 2026-10-16. Independent read-only review performed after implementation.

| ID | Severity | Location | Finding | Resolution |
| --- | --- | --- | --- | --- |
| A1 | LOW | tasks T011/T012 | References omitted the later dependency requirement FR-009 and SC-006. | References corrected after the read-only analysis. |
| A2 | HIGH release blocker | FR-009 / constitution VII | Full npm audit fails on development dependencies; the production-only audit passes. Advisory fixed versions were not installable from the official registry. | Keep the complete audit failure explicit; do not introduce exceptions or incompatible downgrades. Track release remediation in convergence. |
| A3 | HIGH corrected | FR-010 / notice inventory | Extras-qualified requirements omitted HTTPX/PyJWT and CRLF lock bytes would differ on CI checkout. | Strict requirement parsing and malformed-record regressions, LF lock bytes, normally regenerated complete 57-component inventory and updated distribution contract. |

## Coverage

| Requirement / criterion | Tasks |
| --- | --- |
| FR-001, FR-002, SC-001 | T003, T009 |
| FR-003, SC-002 | T004, T009 |
| FR-004, SC-002 | T005, T009 |
| FR-005, SC-003 | T006 |
| FR-006, SC-003 | T007 |
| FR-007, SC-004 | T001, T008 |
| FR-008, SC-005 | T009–T012 |
| FR-009, SC-006 | T013, T014 |
| FR-010, SC-007 | T015 |

All 10 functional requirements and 7 success criteria have task coverage (17/17,
100%). All 4 user stories are covered. No unmapped tasks, material duplication,
contradictory authority, schema changes, or constitution amendments were found.

SC-006 permits recording unavailable fixes; this does not satisfy the constitution's
separate release vulnerability gate. Source checks on this workstation likewise
do not establish packaging, artifact SBOM/provenance, signing or supported-OS
installer acceptance. Those retain independent release outcomes.

The plan justifies the bounded changes and identifies existing large modules for
future decomposition. This pass must not be described as splitting every module
or as establishing production release eligibility while the audit fails.
