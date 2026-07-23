# v1.2 release convergence

Date: 2026-07-22

Decision: source, application-readiness implementation, demo and local quality gates converge as a
v1.2.0 release candidate. Publication remains unauthorized until protected-branch CI, native matrix
rehearsal and verified tag requirements pass on the exact release commit.

| Area | Evidence | Result |
| --- | --- | --- |
| Version identity | Seven authoritative sources agree on 1.2.0 and release-date fixtures agree on 2026-07-22 | Converged |
| Product behavior | FR-040–FR-044 map to an owned deterministic service, canonical exports, clear UI and a complete revision-safe repair path | Converged |
| Privacy and integrity | No inference/network dependency; tenant isolation, exact digests, redaction, hostile Markdown escaping and content-free audit events are tested | Converged |
| Demonstrability | The fictional local seed reaches readiness 100/100 and the real Chromium tour records the open application rather than a presentation page | Converged |
| Local release gates | Final broad and focused gates passed as recorded in release evidence; verified readiness with 300 facts measured 17.805 ms p95 against 100 ms | Converged locally; protected-branch CI and native rehearsal remain publication gates |
| Remote publication | Protected-branch result, native packages, hosted attestations, verified annotated tag and immutable GitHub Release do not yet exist for this candidate | Pending external gate |

No code in this work creates a tag or mutates a remote Release. The v1.1 durable publication
contract remains unchanged; v1.2.0 must pass it on the exact authorized commit.
