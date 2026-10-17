# Convergence evidence: Consolidate all work into main

Date: 2026-10-17. Interim outcome: `tasks_appended` (T012–T020, Phase 4).

The assessment covered eight functional requirements, six success criteria,
four outcomes, eight plan decisions and all eight constitution principles.
All fourteen FR/SC items have task coverage. The initial eleven tasks already
tracked dependency compatibility, full verification, publication and cleanup.

Independent analysis identified one additional structural remediation: the
recovered provider service and schema modules need decomposition to meet the
preferred size without relying on an unapproved exception. The convergence
operation appended T012 to tasks.md. A later real provider API journey exposed a
Unicode-mask encoding defect missed by shared-constant test expectations; its
separate convergence pass appended only T013. Plan clarification, completion
checkboxes and evidence documents were updated separately.
The protected PR then surfaced a GitGuardian finding for the synthetic temporary
test account. Independent source-flow review established its local fixture
provenance; a separate pass appended T014 to replace the fixed password with a
per-run generated value, without dismissing or suppressing the scanner result.
T014 passed its real provider journey and lint, with independent review of the
two-line test-only change. The first real shipping image scan then identified six
fixable HIGH findings; its separate convergence pass appended only T015 for the
Go, x/net and Ubuntu OpenSSL updates, retaining the existing strict gate.
Native package and Agent Access acceptance jobs then exposed two separate gaps:
Rust/npm Tauri version synchronization and clean-host tooling bootstrap. Their
independent convergence assessments append T016 and T017 respectively. The
broader acceptance failures are retained exactly and are not inferred passing
from earlier wheel/unit checks.

T006 and T012 are complete. The installed grouped frontend updates pass full and
production npm audits, the peer tree and all thirteen production licenses. Actual
deferred router loading removed unused login code and the final build passes the
unchanged budgets. All new provider modules are below 300 lines, with unchanged
schema/OpenAPI/function contracts and 186 passing focused regressions. The first
updated axe run also found a language-label mismatch; its narrow accessibility
fix passes the final 686-test frontend suite and affected browser flow.

T009 independent analysis is complete. The final local backend passed 2,940 tests
with 17 skips and 82.03% combined coverage; the first Linux CI backend passed
2,946 tests with 11 skips and 83.59%. T008 remains open until the final protected
remote checks finish. All eight browser groups,
686 frontend tests, static/native/migration/audits, four performance gates, notice
reproduction and clean post-fix installed wheel/protocol/resource proof passed; exact evidence is
in validation.md. No interrupted or failed earlier run is counted as a pass.
T013 is complete: independent pre-split constant/string comparison found exactly
one encoding defect, the ASCII-escaped fix restores all original literal values,
and 267 provider/contract tests pass with a new independent wire expectation.
The interrupted pre-fix complete run is superseded, never reported as passing.
T015–T017 have focused implementation evidence: patched Ollama module/package
contracts, matched Tauri versions with reproduced notices and native gates, and
clean-host tooling bootstrap with a complete Python 3.13 smoke. The separate
Python 3.12 Windows temporary-DLL cleanup failure is retained exactly. Container
scanning, native packaging and the whole acceptance matrix remain CI obligations.
T010/T011 remain open until protected-main integration, content verification,
final recovery preservation and branch cleanup actually finish. PR #112 is now
merged with a verified signature and exact reviewed source tree. All six mandatory
checks, all six Agent Access jobs and both Linux package smokes passed. T015 and
T016 are complete: the actual image has zero HIGH/CRITICAL findings and native
version preflight/build passed. Ten obsolete dependency branches were removed
automatically after their PRs closed, and the preserved local integration branch
was removed. A new automated two-patch branch appeared during cleanup, so a
separate convergence pass appended only T018. The deletion guard stopped on the
changed inventory; the new tip is bundled and its compatible patches, truthful
icon provenance and lock-bound notices are assessed before final publication.
The same automation wave later produced a separate Python branch containing nine
direct upgrades but no regenerated locks. A further convergence pass appended
only T019 before implementation; the existing compatibility, lock, notice and
complete verification requirements apply. No new authority or waiver is added.
Review of the official FastAPI source identified newly built-in instrumentation
that can use ambient providers even without an exporter dependency. A separate
assessment appended T020 before implementation: explicit five-control opt-out and
adversarial privacy tests are required to preserve the existing constitution.
T018 now passes 686 frontend tests, all eight browser groups, lint/build and
lock-bound legal/icon checks. T019 has a verified exact 121-package environment,
coherent 58/112/21 locks and three zero-finding audits. T020 meaningfully reproduced
18 ambient instrumentation/setup events before the five-control guard and passes
with zero afterward. Final static checks and applicable hooks pass. A frozen
complete Windows backend run and the remaining API/protected gates must finish;
earlier integration results do not substitute for those changed-dependency gates.

The old unavailable-package inference is withdrawn after independent fresh-cache
registry checks; historical failed scans are retained as executions, not treated
as current availability proof. Actual shipping image/native release evidence
must still be supplied by the applicable workflows before claiming a production
release. Existing release obligations are not new product scope or a new waiver.
