# Backup assurance center — convergence

Date: 2026-07-24

Decision: the constitution, specification, plan, tasks, API, recovery interface, native shell, tests,
and owner documentation now use the same backup model. Inspection proves structural usability
without mutation. Restore is a later empty-vault operation. Desktop save success means the final
destination bytes were re-read and matched the server digest.

| Area | Converged behavior | Result |
| --- | --- | --- |
| Product language | “Valid,” “compatible,” and “restorable” are separate claims; ZIP confidentiality and authorship limits are explicit | Converged |
| Inspection | Supported archives receive full preflight with no database or managed-file writes | Converged |
| Response privacy | Counts, byte totals, digest, time, booleans, and stable codes are the entire response surface | Converged |
| Historical data | Versions 1–4 remain inspectable; application projections are rebuilt from their snapshot and timeline | Converged |
| Restore | The existing explicit endpoint keeps empty-vault, lock, quarantine, transaction, and rollback requirements | Converged |
| Desktop save | Bounded raw IPC enters one native command; random sidecars, file flush, read-back hash, promotion, final verification, and rollback are enforced | Converged |
| Filesystem authority | Rust opens the save dialog and retains the chosen path; JavaScript has no save-dialog or filesystem mutation capability | Converged |
| Browser save | The UI makes no final-destination verification claim | Converged |
| Accessibility | The bilingual summary has labelled structure, keyboard-operable actions, status feedback, and an automated accessibility gate | Converged |
| Persistence | No database migration is needed | Converged |
| Documentation | README, privacy, architecture, daily-driver, specification, and constitution describe the implemented guarantees and limits | Converged |
| Quality gates | Backend, frontend, Rust library, static, build, license, and diff gates passed locally | Converged locally |

Publication still requires protected-branch CI and the existing signed-tag workflow on the exact
merged commit. Packaged smoke evidence must continue to come from the allowed release runner, and
no manual artifact may bypass those controls.
