# Application readiness convergence

Date: 2026-07-22

Decision: the Application Readiness Pack converges locally against FR-040–FR-045 and SC-014–SC-015. It is
ready for protected-branch CI and native release rehearsal; no tag or external release was created.

| Requirement | Implementation | Verification | Result |
| --- | --- | --- | --- |
| FR-040 deterministic local report | `backend/applications/readiness.py` derives nine checks from the owned snapshot, local profile and immutable resume only | Incomplete and 100/100 fixtures; seed runs with the model endpoint deliberately unreachable | Converged |
| FR-041 inspectable completeness | Stable identifiers, pass/warning/blocker state, points, evidence, action, source revision and fingerprint are returned; UI says this is not hiring probability or candidate quality | Backend score/status assertions and frontend accessible rendering tests | Converged |
| FR-042 meaningful preflight | Role identity/detail, application route, profile, published resume, verified artifact bytes, publication quality, freshness and selected-fact verification are checked | Real PDF/DOCX plus deleted, corrupt, escaping, unreadable and length-mismatch cases in the backend suite | Converged |
| FR-043 canonical safe exports | JSON and Markdown are serialized canonically, fingerprinted without self-reference and served with an exact body SHA-256 plus safe filename | Repeated byte equality, digest, header, redaction and hostile-title tests | Converged |
| FR-044 repair without recreation | Expected-revision PATCH edits title, company, description, URL, email and owned resume link through a conditional write; audit payload contains field names only | Successful repair, stale writer, no-op, invalid URL/email, foreign resume and editor submission tests | Converged |
| FR-045 accessible Application Detail | A body portal provides labelled modal semantics, a dynamic focus trap, Escape, inert/scroll lock, connected-opener restoration and mobile-safe viewport/overscroll behavior | Axe, keyboard traversal through dynamically inserted editor controls, cleanup, focus-return and update-without-unmount tests | Converged |
| SC-014 deterministic acceptance | API and UI provide deterministic state, accurate counts, matching downloads and direct remediation | Full backend/frontend coverage, static/build/Rust/migration gates and a real-app demo recording passed | Converged |
| SC-015 integrity and keyboard acceptance | Artifact availability requires contained, readable, digest- and length-matched bytes; the modal retains focus through dynamic controls | Adversarial artifact fixtures; dedicated portal keyboard tests; and a 300-fact, real PDF/DOCX benchmark at 17.805 ms p95 against 100 ms passed | Converged |

The [cross-artifact analysis](application-readiness-analysis.md) records the reviewed boundaries and
resolved findings. The [v1.2 release preparation](release-evidence-v1.2.0.md) records the exact local
commands and results. Remote branch protection, six-platform native rehearsal, attestations, signing
and immutable publication remain mandatory before calling v1.2.0 released.
