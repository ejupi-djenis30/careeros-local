# v1.3 release convergence

Date: 2026-07-22

Decision: source, daily-driver implementation, demo and local quality gates converge as a v1.3.0
release candidate. Publication remains unauthorized until protected-branch CI, native matrix
rehearsal and verified tag requirements pass on the exact release commit.

| Area | Evidence | Result |
| --- | --- | --- |
| Version identity | Seven authoritative sources agree on 1.3.0 and release-date metadata agrees on 2026-07-22 | Converged |
| Deterministic search | Provider queries are derived only from explicit inputs, versioned cache provenance is enforced and `no_explicit_queries` is represented in the UI | Converged |
| Application workflow | Bounded summaries, canonical projections, typed next actions, calendar exports and evidence dossiers share tested revision and ownership contracts | Converged |
| Portability | Historical rows rebuild from snapshots/events; complete current-v3 projections are validated; inconsistent archives roll back | Converged |
| Error semantics | Resume metadata loading, empty and error states remain distinct; transport failures never masquerade as zero evidence | Converged |
| Demonstrability | The fictional local seed drives the real application; regenerated WebM, GIF, poster and screenshots contain no personal identity | Converged |
| Local release gates | 1,090 backend tests, 300 frontend tests, 10 Rust tests, static checks, migration replay, production build and all four performance tests passed | Converged locally; protected-branch CI and native rehearsal remain publication gates |
| Remote publication | Protected-branch result, native packages, hosted attestations, verified annotated tag and immutable GitHub Release do not yet exist for this candidate | Pending external gate |

No code in this work creates a commit, tag or remote Release. The durable publication contract and
historical v1.2 evidence remain unchanged; v1.3.0 must pass the same remote controls on the exact
authorized commit.
