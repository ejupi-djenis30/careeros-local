# Job library and Application pipeline — convergence

Date: 2026-07-26

Decision: API schemas, Job models, Job repository/service behavior, Application writes,
architecture documentation, functional requirements, and tests converge on one user-owned logical
opportunity and one authoritative Application pipeline.

| Area | Converged behavior | Result |
| --- | --- | --- |
| Response | Every Job can expose nullable owned Application id and stage | Converged |
| Isolation | Shared scraped listings do not expose another user's Application | Converged |
| Duplicate Jobs | One Application resolves across search-profile duplicates | Converged |
| Creation | A second Job-backed Application for the same logical opportunity is rejected | Converged |
| Storage race | Nullable logical identity plus user-scoped uniqueness closes concurrent-create races | Converged |
| Legacy migration | All timelines survive; only the latest deterministic duplicate receives the logical identity | Converged |
| Pagination | Distinct tracked-opportunity count remains stable across pages | Converged |
| Marker projection | Applied milestones synchronize all duplicate legacy markers monotonically | Converged |
| Early and terminal stages | Saved/preparing remain unapplied; post-apply withdrawn/archived remain applied | Converged |
| Manual pipeline | Manual Applications remain independent and do not inflate Job tracking counts | Converged |
| Portability | Export and restore preserve/remap logical identity even after the source Job is removed | Converged |
| Archive contract | v5 declares the new row shape while the decoder keeps v1–v4 restore compatibility | Converged |
| Legacy API | PATCH remains available, deprecated, and does not create an Application | Converged |
| Verification | Application, Job, Ruff, and mypy gates are required before handoff | Pending local verification |

This document records local implementation convergence only. Protected-branch CI and the signed
release workflow remain the publication gates.
