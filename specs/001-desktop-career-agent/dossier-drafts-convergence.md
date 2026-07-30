# Durable application dossier drafts — convergence

Date: 2026-07-29

Decision: the constitution, specification, plan, tasks, data model, OpenAPI contract,
implementation, tests and owner documentation now use the same dossier model. A draft is a bounded
mutable local working copy; publication is an immutable Application event that consumes only the
exact saved draft in the same transaction.

| Area | Converged behavior | Result |
| --- | --- | --- |
| Product language | Autosave describes local SQLite persistence, not cloud storage or browser storage | Converged |
| Persistence | One revisioned draft is allowed per Application and remains separate from immutable timeline events | Converged |
| Ownership | Every operation resolves the authenticated user's Application and owned linked Resume Version | Converged |
| Save semantics | Create and update compare revisions and re-check the Application/Resume binding while holding the writer transaction | Converged |
| Conflict semantics | Stale writers change neither the saved draft nor the visible local form; retry and deliberate rebase remain explicit | Converged |
| Publication | Workspace publication saves first, compares the exact draft projection and deletes that row only with the immutable event commit | Converged |
| Compatibility | Direct API publication remains available only when no working draft exists | Converged |
| API | Authenticated private/no-store GET, rate-limited PUT and rate-limited DELETE match OpenAPI 1.2.0 | Converged |
| Frontend | Bilingual restore, autosave, retry, conflict, discard and publish states are accessible and tested | Converged |
| Portability | Format v6 includes drafts; preflight rejects incomplete, malformed, duplicated or disconnected rows before writes | Converged |
| Historical data | Formats v1–v5 remain inspectable and restorable with no synthesized draft rows | Converged |
| Erasure | Application deletion and complete vault erasure remove associated drafts | Converged |
| Migration | Upgrade, one-step downgrade and re-upgrade pass against an isolated SQLite database | Converged |
| Documentation | Architecture, privacy, daily-driver, changelog and Spec Kit artifacts state the same guarantees and limits | Converged |
| Quality gates | Backend, frontend, Rust, static analysis, OpenAPI parsing, migration and diff gates passed locally | Converged locally |

Release publication still requires protected-branch CI, packaged smoke evidence and the existing
signed release workflow on the exact integrated commit. Portable ZIP confidentiality and authorship
remain explicit out-of-scope guarantees.
