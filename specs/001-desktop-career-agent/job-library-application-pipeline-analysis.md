# Job library and Application pipeline — cross-artifact analysis

Date: 2026-07-26

## Decision under review

CareerOS now presents discovery and application tracking as one workflow. Several Job rows may
represent the same provider listing across search profiles, but one user-owned Application is the
authoritative pipeline for that logical opportunity.

## Contract

| Boundary | Required behavior |
| --- | --- |
| Job response | `application_id` and `application_stage` expose the owned pipeline or `null` |
| Ownership | Application resolution filters both Job and Application by the authenticated user |
| Logical identity | Duplicate Job rows are unified through their shared `scraped_job_id` |
| Pagination | `total_tracked` counts distinct filtered logical opportunities with an Application and is independent of page size |
| Query shape | Application links are resolved in one bulk query, never once per Job row |
| Creation | `ApplicationService.create` rejects a second Application reached through any duplicate Job row |
| Storage enforcement | The database permits at most one non-null `(user_id, scraped_job_id)` Application, including concurrent creates |
| Archive version | New exports use v5; v1–v4 remain readable and v5 never masquerades as the older v4 row contract |
| Manual Application | A manual Application without `job_id` remains valid and does not appear as a tracked Job opportunity |
| Applied milestone | Applied and subsequent active/outcome stages set every duplicate Job marker in one transaction |
| Early stages | Saved and preparing do not set the legacy marker |
| Terminal stages | Withdrawn or archived preserve a marker only when the timeline previously crossed applied |
| Legacy API | Job PATCH remains compatible and deprecated, never creates an Application, and cannot erase an Application-backed milestone |

## Compatibility

`applied`, `applied_elsewhere`, and `total_applied` remain in the response for existing clients.
They describe legacy Job-row markers. New clients use `application_id`, `application_stage`, and
`total_tracked` for pipeline state. `Application.scraped_job_id` keeps the logical opportunity
stable even when the originating Job row is removed. The database enforces one non-null logical
identity per user, while multiple manual Applications remain valid because their identity is
`NULL`.

## Legacy data

New writes cannot create a second Application for one user's logical opportunity, even when two
transactions pass the service pre-check concurrently. The migration keeps every older timeline. If
an older vault already contains conflicting Applications on duplicate Job rows, the most recently
updated row receives the new logical identity (lowest id wins an exact timestamp tie) and the other
rows retain a `NULL` identity. Reads use the same deterministic rule while mixed-version data is
possible. Portable restore remaps shared listing ids and applies this rule before inserting rows.
No timeline is deleted or merged.

## Failure behavior

Creating against an unowned or missing Job fails before a snapshot is written. Creating through a
duplicate Job returns the existing conflict response; a storage-level uniqueness race is translated
to the same response after rollback. A standalone manual Application bypasses Job resolution by
design. Clearing a legacy marker remains possible only when no owned Application timeline has
crossed the applied milestone.
