# Data model

## `campaigns`

| Column | Type | Constraints / meaning |
|---|---|---|
| `id` | UUID string | primary key |
| `user_id` | integer | FK users, cascade; ownership boundary matching the canonical `users.id` type |
| `name` | string | user-visible campaign name |
| `source_fingerprint` | 64-char hex | unique with `user_id` |
| `tracker_sha256` | nullable 64-char hex | digest of tracker member |
| `summary` | JSON | bounded aggregate counts/warnings only |
| `created_at` | UTC datetime | import time |
| `updated_at` | UTC datetime | standard mutation timestamp |

Indexes: unique `(user_id, source_fingerprint)`, `(user_id, created_at)`.

The `tracker` artifact binds to a deterministic reconstructed Applications-only XLSX. It never
binds to the original credential-bearing tracker bytes, even though `Campaign.tracker_sha256`
records the source member digest.

## `campaign_applications`

| Column | Type | Constraints / meaning |
|---|---|---|
| `id` | UUID string | primary key |
| `campaign_id` | UUID string | FK campaigns, cascade |
| `application_id` | UUID string | FK applications, cascade |
| `source_application_id` | string | original ID; unique in campaign |
| `source_order` | integer | stable tracker/dossier order |
| `source_status` | nullable string | verbatim tracker status |
| `priority` | nullable string | verbatim priority |
| `platform` | nullable string | source/platform projection |
| `category` | nullable string | job-category projection |
| `outcome` | nullable string | outcome projection |
| `found_at` | nullable date | parsed projection |
| `applied_at` | nullable date | parsed projection |
| `follow_up_at` | nullable date | parsed tracker follow-up projection |
| `last_update_at` | nullable date | parsed projection |
| `tracker_record` | JSON object | all 28 original header/value pairs; strings, ISO date strings, booleans, finite numbers or null |
| `provenance` | JSON object | `tracker`, `dossier`, or both plus parser warnings |

Unique keys: `(campaign_id, source_application_id)`, `(campaign_id, application_id)`.
Indexes: `(campaign_id, source_order)`, `(campaign_id, priority)`, `application_id`.

## `campaign_artifacts`

| Column | Type | Constraints / meaning |
|---|---|---|
| `id` | UUID string | primary key |
| `campaign_id` | UUID string | FK campaigns, cascade |
| `application_id` | nullable UUID string | FK applications, set null/cascade decision documented in migration |
| `asset_id` | UUID string | FK career_assets, restrict while referenced |
| `relative_path` | canonical string | unique within campaign; never an OS path |
| `display_name` | string | safe final component for download |
| `category` | enum-like string | tracker, profile, goal, story, credential, template, vacancy, cv, letter, email, evidence, image, script, other |
| `source_order` | integer | deterministic listing order |
| `created_at` | UTC datetime | import time |

The category `credential` is reserved for validation and MUST never be persisted.

## Existing entity changes

- `CareerAsset.kind` admits `campaign_document`; canonical publication path is
  `assets/campaign/{sha256[0:2]}/{sha256}`.
- `ApplicationSummary` may expose nullable campaign projections (`campaign_id`,
  `source_application_id`, `campaign_priority`, `campaign_platform`) through a bounded join.
- Existing Job, Application, ApplicationEvent, ApplicationTask, SourceDocument and CandidateProfile
  schemas remain canonical for operations.

## State mapping

| Source | CareerOS event path |
|---|---|
| Saved | `saved` |
| Preparing | `saved → preparing` |
| Applied | `saved → preparing → applied` (event timestamps use available source dates) |
| Closed after application | `saved → preparing → applied → archived` |
| Closed without application evidence | `saved → archived` |
| Dossier only, prepared | `saved → preparing` |

Every event is append-only and carries only bounded provenance identifiers, not full document text.

The initial `saved` event is application revision 1; every later stage event and optional imported
task advances the revision once. Imported stage events contain only an import marker and the source
application ID. Date-only tracker values use 12:00 UTC and are normalized into a strictly increasing
timeline no later than the import instant. Active, non-closed tracker records with a non-blank next
action receive exactly one pending task; its optional due time is the follow-up date at 12:00 UTC.
Closed and dossier-only records receive no imported task.

## Portability v8

Export order after existing core rows:

1. `campaigns` after the user/profile dependencies;
2. jobs/applications and career assets;
3. `campaign_applications` after campaigns and applications;
4. `campaign_artifacts` after campaigns, applications and career assets;
5. dependent events/tasks/drafts in the established safe order.

Inspection validates ownership, UUIDs, uniqueness, all FKs, JSON shapes, digests, managed paths and
campaign-asset bindings. Restore publishes asset bytes through the existing journal before marking
the vault ready.
