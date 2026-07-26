# Career Vault search source — convergence

Date: 2026-07-26

Decision: API schemas, persistence, Career Vault services, search orchestration, privacy
documentation, architecture documentation, and tests converge on one immutable-source rule: a new
campaign captures candidate evidence once, and a rerun uses that exact saved evidence.

| Area | Converged behavior | Result |
| --- | --- | --- |
| Source selection | Explicit source wins; otherwise CV text preserves legacy upload behavior and an empty value selects the Vault | Converged |
| Vault evidence | Only confirmed, non-archived, non-private facts enter a bounded deterministic snapshot | Converged |
| Privacy | Contacts, birth date, nationality, references, links, draft facts, and archived facts are excluded or redacted | Converged |
| Persistence | Exact snapshot text and non-sensitive source provenance are stored with search history | Converged |
| Reruns | Saved snapshot and metadata remain unchanged after later Vault edits | Converged |
| Compatibility | Uploaded-CV campaigns and legacy history records remain usable | Converged |
| Provider isolation | Candidate evidence remains local and absent from acquisition queries | Converged |
| Schema | Existing columns are reused; no database migration is needed | Converged |
| Verification | Career and search suites: 127 passed; contract route slice: 44 passed; Ruff and targeted mypy passed | Converged locally |

Targeted mypy passed with normal import following. This document records local implementation
convergence only. It does not replace protected-branch CI or the signed release workflow.
