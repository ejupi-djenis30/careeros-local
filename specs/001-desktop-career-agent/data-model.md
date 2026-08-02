# Data Model: CareerOS Local Desktop Career Agent

## Persistence boundaries

- The career vault is the canonical SQLite database under the OS application-data directory.
- Attachments, photos, resume artifacts, models and runtime binaries are content-addressed or
  integrity-manifested files beside the database, never database blobs.
- Raw session tokens, raw JWT identifiers, ports, process identifiers and active download progress
  are ephemeral and MUST NOT be written to the vault. The browser auth boundary persists only the
  SHA-256 digest of the one currently valid refresh JTI in each bounded session family; access
  JTIs are never persisted.
- Prompts and model outputs are never stored in AI audit tables; trusted product records store
  only the accepted domain result already required by the user workflow.

## Existing entities retained

### Career Vault

Aggregate over users, candidate profile, career facts, evidence sources, assets, goals, jobs,
applications, workflows, coach conversations, resume drafts, immutable versions and exports.
Backup manifests include schema version, record counts and content hashes.

### User vault lifecycle

The owner row is the durable recovery boundary. Normal session authority exists only in `ready`;
the other states survive process loss before destructive work begins.

| Field | Type | Rules |
|------|------|-------|
| `vault_lifecycle_state` | short string | Required; exactly `ready`, `reset_pending`, `restore_pending` or `erasure_pending`; indexed |
| `vault_maintenance_fingerprint` | 64-char hex nullable | Required only for `restore_pending`; lowercase SHA-256 of the verified archive |

Database checks bind state and fingerprint: `restore_pending` requires one canonical fingerprint,
while every other state requires `NULL`. Transitions to pending commit before mutation. Reset and
erasure repeat family revocation under the same owner-row serialization before returning to
`ready` or deleting the owner. Restore returns to `ready` in the same commit that restores records,
revokes sessions and grants, and leaves imported schedules disabled.

### Auth Session

`AuthSession` is content-free server-side authority for one browser access/refresh family. It is
not part of the portable career archive. Phase T reuses this existing schema and requires no new
table, column or migration.

| Field | Type | Rules |
|------|------|-------|
| `id` | 32-char hex | Non-secret family id (`sid`), primary key, signed into both access and refresh JWTs |
| `user_id` | integer | Required owner, cascade delete with User |
| `slot` | integer | 0–7; unique with `user_id`, enforcing eight rows per account |
| `refresh_jti_digest` | 64-char hex | Unique SHA-256 of the only current JTI; raw JTI is never stored |
| `expires_at` | UTC timestamp | Current refresh expiry |
| `revoked_at` | UTC timestamp nullable | Set by replay, logout or restore |
| `created_at` | UTC timestamp | Family issuance time used for deterministic capacity eviction |
| `updated_at` | UTC timestamp | Last rotation or revocation |

State transition:

```text
issued(current digest A) -> rotated(current digest B) -> rotated(current digest C)
          |                          |                           |
          +-> logout/replay --------+---------------------------+-> revoked
          +-> expiry/capacity eviction/complete erasure ----------------> removed
```

Rotation is one conditional database update over family, owner, current digest, non-revoked state
and expiry. A zero-row update followed by a live family with a different digest is replay and
revokes that family. Restore revokes only the restored user's rows. Complete erasure removes only
the erased user's rows. Every protected access first validates the JWT's own expiry and then uses
one indexed join to require this row's `id`, owner subject, non-revoked state and refresh-family
expiry. A committed revoke or delete therefore denies all later access requests for that `sid`;
work already authorized before the commit is not retroactively cancelled. The access JTI remains
ephemeral because family-level authority is sufficient—there is no per-access-token blacklist.
During reset or restore recovery, a live family may anchor only a signed, non-refreshable
`vault_maintenance` access bearer. During erasure recovery the family is represented by a revoked
sentinel whose digest is derived from its id; maintenance dependencies recognize it only in the
matching durable state. Logout deletes that exact sentinel so the presented bearer cannot regain
authority. A new correct-password login may replace it, but purpose-bound tokens never authorize
ordinary routes, refresh, automation authentication or grant issuance.

### Provider Listing Observation

The shared `ScrapedJob` catalog keeps provider content separate from private per-user decisions.
Alongside the normalized listing fields it stores:

| Field | Type | Rules |
|------|------|-------|
| `first_seen_at` | UTC timestamp | Set on first successful observation; never moves forward |
| `last_seen_at` | UTC timestamp | Updated on every successful observation |
| `last_changed_at` | UTC timestamp | Updated only when canonical listing content changes |
| `content_revision` | integer | Starts at 1 and increments once per accepted content change |

Canonical content consists of title, company, location, workload and description. Provider
observations upsert this catalog row before private profile deduplication. A content change makes a
previously seen opportunity eligible for normalization and local-model analysis again; existing
analysis is trusted only when its stored input fingerprint still matches the current catalog
content. Each queued observation carries the persisted catalog id, revision and fingerprint.
User-scoped `Job` persistence rechecks that tuple immediately before mutation and skips stale or
missing observations without a second catalog upsert. Local-model normalization captures the same
tuple before inference, then reloads and locks the row before applying success or failure fields;
output for an older tuple is discarded. Refreshing a catalog row never mutates `Job` decisions,
`Application` workflow state or the immutable listing snapshot stored with an application.

Absence is not an observation: a missing page result, provider error, truncated response or
different query cannot close a listing. Existing rows migrate to revision 1 with all observation
timestamps copied from `created_at`, deliberately making no statement about earlier history.

### Search Completion Receipt

`SearchProfile` retains a minimal receipt independently of the 24-hour polling payload:

| Field | Type | Rules |
|------|------|-------|
| `last_search_started_at` | UTC timestamp nullable | Stable idempotency key for the last success |
| `last_search_completed_at` | UTC timestamp nullable | Written only with a real `done` transition |
| `last_search_state` | short string nullable | `done` only |
| `search_run_count` | integer | Starts at 0; increases once per distinct successful run |
| `last_search_summary` | JSON nullable | Fixed versioned schema, maximum 4096 serialized bytes |

The summary contains only canonical UTC times, bounded duration, bounded aggregate counters and the
aggregate provider state `not_contacted`, `succeeded`, `partial` or `failed`. Its builder uses a
positive whitelist and never reads CVs, queries, listing descriptions, logs, errors or raw provider
data. Runtime status and a new receipt commit together. Error, stop and cancellation updates touch
only runtime status, and pruning runtime columns leaves the receipt unchanged.

### Search Profile Overview Projection

List and workspace-status surfaces read a separate authenticated projection instead of serializing
`SearchProfile`. Items are ordered by `created_at DESC, id DESC`, use bounded page parameters and
contain only id, display/search labels, schedule controls, selected filter preferences, history
state and creation time. They never contain CV text, cached prompts or queries, profile snapshots,
normalization payloads, raw advanced preferences or runtime locks.

The response also contains an aggregate computed across every profile owned by the authenticated
user, not merely the current page: profile count, successful-run count and the latest successful
receipt's profile id, start/completion times, jobs-found count and bounded summary. Consumers that
need full historical profile details continue to use the compatibility history endpoint.

### Application Logical Opportunity

`Application.scraped_job_id` is a nullable foreign key to the shared provider listing with
`ON DELETE SET NULL`. A unique constraint on `(user_id, scraped_job_id)` permits one authoritative
pipeline per user and listing, even when several private `Job` rows represent that listing across
search profiles. Manual Applications keep this field `NULL`, so users can still track multiple
opportunities entered by hand.

The migration preserves conflicting legacy timelines. For each user and listing, it assigns the
logical identity only to the most recently updated Application, using the lowest Application id as
the deterministic tie-breaker, and leaves other historical timelines with `NULL`.

### Candidate Profile

One per local user. Core fields include display identity, headline, summary, contact visibility,
location, work authorization, links, photo asset, revision and preferences. Structured history
is represented by ordered `CareerFact` records so every item can carry evidence and confidence.

### Career Fact

Fields: UUID, profile UUID, type, order, validated payload, source-document UUID, source locator,
confidence, verification state, archive timestamp and normal timestamps.

Allowed type families include experience, achievement, skill, project, education, certification,
language, publication, award, volunteering, membership, reference and portfolio. Payload schemas
remain type-specific and reject unknown high-risk keys.

State transition:

```text
draft -> confirmed -> archived
  |          |
  +-> rejected
```

Only confirmed facts are selected automatically for trusted resume claims. Draft facts may be
used only when the user explicitly includes them and the output remains marked for review.

### Career Goal

Fields: UUID, profile UUID, name, primary flag and versioned payload. The payload contains target
roles, domains, locations, work modes, compensation, deadline, priority, constraints, milestones,
actions, skill gaps, evidence links and progress. Milestone/action identifiers are stable inside
the payload so UI edits and imports can merge safely.

### Resume Draft and Resume Version

A draft holds editable content selection, overrides and canvas document. Publishing creates an
immutable version with profile revision, selected fact IDs, content/layout snapshot, quality
report, renderer version and content hash. PDF/DOCX artifacts are immutable children.

Canvas invariants:

- schema version is mandatory;
- every block has a stable ID, section, fact references, page hint and bounded geometry;
- ATS templates reject photo blocks and multi-column coordinates;
- hidden blocks remain recoverable in the draft but do not render;
- publishing fails on unsupported evidence references or silent overflow.

## New persistent entities

### JobProviderConfiguration

Purpose: one user-owned, revisioned provider installation. It either declares a public JSON/HTML
adapter or references a reviewed native adapter through a bounded imported document or pack.

| Field | Type | Rules |
|------|------|-------|
| `id` | UUID | Primary key |
| `user_id` | integer | Required owner; cascade delete; indexed with enabled state |
| `key` | short string | Unique per owner; normalized provider identifier |
| `display_name` | string | Printable, 1–160 characters |
| `description` | text | Bounded routing description |
| `adapter_kind` | `json`, `html` or `native` | Check constrained; selects a strict parser or closed native factory |
| `native_adapter_id` | nullable short string | Required only for native rows; allowlisted identifier, never a module/path |
| `source_pack_id` | nullable short string | Bounded import provenance |
| `source_pack_version` | nullable short string | Bounded pack version provenance |
| `enabled` | boolean | Explicit consent for this source to participate in searches |
| `revision` | positive integer | Monotonic compare-and-swap authority |
| `request_config` | nullable JSON object | Required for declarative rows; HTTPS origin, templates, confidential headers and hard limits |
| `extraction_config` | nullable JSON object | Required for declarative rows; JSON paths or bounded CSS mapped to canonical job fields |
| `capabilities_config` | JSON object | Bounded accepted domains and supported languages |
| `created_at` | timestamp | UTC |
| `updated_at` | timestamp | UTC |

Fresh users have no rows. A provider document or pack validates every entry and conflict before one
atomic insert; imported rows default to disabled unless the import explicitly activates them.
Declarations cannot contain code, arbitrary regex, redirects, ambient proxy settings, filesystem
paths or an alternate network origin. Runtime resolution rejects local, private, link-local and
otherwise non-public addresses immediately before every request. Every configured header value is
confidential: API and MCP views return only a preservation marker, and portable archive v7 removes
all headers and disables imported providers until the owner explicitly re-enables them.

### AIExecution

Purpose: content-free audit and quality telemetry for a local AI task.

| Field | Type | Rules |
|------|------|-------|
| `id` | UUID | Primary key |
| `user_id` | integer nullable | Cascade delete with local user; null for evaluation |
| `task` | short string | Controlled task identifier |
| `contract_version` | short string | Semantic version of structured output contract |
| `model_id` | string | Local runtime/model identifier only |
| `input_fingerprint` | 64-char hex | Hash of canonical references, never raw input |
| `output_fingerprint` | 64-char hex nullable | Hash of accepted canonical output |
| `evidence_count` | integer | Non-negative |
| `accepted` | boolean | True only after every validator passes |
| `repair_count` | integer | 0 or 1 |
| `validation_codes` | JSON array | Controlled non-sensitive error codes |
| `duration_ms` | integer | Non-negative monotonic duration |
| `prompt_tokens` | integer nullable | Runtime-reported aggregate |
| `completion_tokens` | integer nullable | Runtime-reported aggregate |
| `created_at` | timestamp | UTC, indexed with task |

No foreign key points to a specific fact because vault deletion/archival must not require
rewriting audit rows. Evidence count and canonical fingerprints are sufficient for diagnostics.

### ApplicationDossierDraft

Purpose: one mutable, private working copy for an Application before immutable dossier publication.

| Field | Type | Rules |
|------|------|-------|
| `id` | UUID | Primary key |
| `application_id` | UUID | Required, unique, cascade delete with Application |
| `resume_version_id` | UUID | Required owned Resume Version; cascade delete |
| `application_revision` | integer | Positive revision against which the draft was saved |
| `revision` | integer | Positive monotonic compare-and-swap revision |
| `content` | JSON object | Strict bounded `ApplicationDossierDraftContent` |
| `created_at` | timestamp | UTC |
| `updated_at` | timestamp | UTC and not earlier than creation in portable archives |

Content retains stable, unique client ids for requirement, answer and checklist rows so incomplete
autosave state can round-trip without relying on array position. Evidence references remain UUIDs
inside bounded JSON because facts may be removed or a linked Resume may change before the user
rebases; publication accepts only confirmed facts present in the currently linked Resume snapshot.

### AIEvaluationRun

Purpose: aggregate evidence that a model profile satisfies release thresholds.

| Field | Type | Rules |
|------|------|-------|
| `id` | UUID | Primary key |
| `dataset_version` | short string | Required |
| `application_version` | short string | Required |
| `model_id` | string | Required local model identity |
| `runtime_version` | string | Required managed/runtime adapter identity |
| `case_count` | integer | Positive |
| `metrics` | JSON object | Validated task and aggregate metrics |
| `passed` | boolean | Computed from versioned thresholds |
| `duration_ms` | integer | Non-negative |
| `peak_memory_bytes` | integer nullable | Non-negative when available |
| `result_fingerprint` | 64-char hex | Canonical aggregate hash |
| `created_at` | timestamp | UTC |

Evaluation rows contain no case prompts or outputs. Those remain synthetic fixtures in source.

## New file-manifest entities

### Restore ownership journal

Per-account JSON copies at `.restore/user-{id}/journal.json` and `journal.backup.json` contain no
document bytes or record payloads:

| Field | Type | Rules |
|------|------|-------|
| `version` | integer | Exact supported journal contract |
| `generation` | positive integer | Monotonic; a newer copy must contain a path superset |
| `user_id` | positive integer | Exact owner namespace |
| `archive_fingerprint` | 64-char hex | Must match durable restore lifecycle state |
| `paths` | sorted string array | Only absent destinations under canonical `assets/` or `resumes/` |
| `checksum` | 64-char hex | SHA-256 of the canonical preceding fields |

Owner-scoped temporary bytes live only in `.restore/user-{id}/staging`. Journal copies are durable
before publication. A valid higher generation can repair a torn lower copy only when owner,
fingerprint and path monotonicity agree; same-generation disagreement, invalid dual copies or a
non-monotonic generation fails closed. Cleanup removes only paths with no current binding from a
different account and then removes the full owner namespace.

### ModelCatalogEntry

Checked-in immutable metadata: key, display name, author, license, capability profile, parameter
count, context ceiling, quantization, byte size, exact download URL, SHA-256, minimum RAM,
recommended RAM and compatible runtime version. URLs are never accepted from API clients.

### RuntimeAsset

Checked-in immutable metadata per OS/architecture: llama.cpp version, archive type, exact URL,
byte size, SHA-256, executable relative path and required adjacent libraries.

### InstalledModelManifest

Atomic local JSON: catalog key, catalog version, model path/hash/size, runtime path/hash/version,
installation timestamp and last successful verification. It contains no user data.

State transition:

```text
absent -> checking_space -> downloading_runtime -> verifying_runtime
       -> downloading_model -> verifying_model -> installing -> ready
       -> starting -> running

Any active state -> cancelling -> absent|ready
Any active state -> failed -> retrying|absent|ready
running -> stopped -> starting|ready
```

Partial files use a `.part` suffix and are excluded from ready manifests. Archive extraction is
to a staging directory with path traversal and link rejection, then atomically renamed.

## Ephemeral desktop entities

### DesktopSession

Fields: 256-bit token, loopback API port, backend child handle, start timestamp, readiness state,
restart count and app-data paths. It lives only in the Tauri process. The frontend receives the
base URL and token through one invoke command; it never persists them.

State transition:

```text
created -> spawning -> waiting_ready -> ready -> shutting_down -> stopped
                         |                 |
                         +-> failed <------+-> restarting (bounded)
```

### StructuredTaskContract

Code-level immutable definition: task ID, semantic version, JSON Schema, system instruction,
context budget, output budget, temperature, evidence policy, semantic validator and repair policy.
Contract versions are stored with audit rows and golden cases.

## Migration

One Alembic revision adds `ai_executions` and `ai_evaluation_runs` plus indexes on
`(task, created_at)`, `(model_id, created_at)` and evaluation `(dataset_version, model_id)`.
Upgrade creates empty audit tables and changes no trusted career data. Downgrade drops only these
content-free tables. Desktop startup performs a pre-upgrade SQLite backup when the current head
differs from the packaged head, applies migrations once under the vault lock, and restores the
backup if migration or readiness validation fails.

A later revision adds the four provider-observation fields to `scraped_jobs`, backfills every
existing row from `created_at` at revision 1, and indexes `last_seen_at`. The backfill is deliberately
conservative: it preserves every listing while making no claim about observations or revisions that
CareerOS could not have recorded before the migration.

The following revision adds the five durable receipt fields to `search_profiles` and indexes the
completion time. A profile is backfilled at count 1 only when its still-present polling state is
`done` and carries coherent start/completion timestamps. Failed, cancelled, expired or ambiguous
history remains null at count 0.

The application-link revision adds the nullable logical-opportunity foreign key and its user-scoped
unique constraint. The next revision restores the database-managed `jobs.updated_at` default that
the earlier SQLite table rebuild had dropped. Its round-trip rebuild preserves data, indexes,
foreign keys and uniqueness while allowing database-level inserts to omit the timestamp again.

The refresh-session revision follows the current dossier-draft head and creates an empty
`auth_sessions` table. It does not backfill stateless refresh JWTs because their raw values and
identifiers were intentionally never persisted; a pre-migration token therefore fails closed and
the existing auth response clears it. The unique `(user_id, slot)` constraint enforces the row cap,
the JTI digest is unique, and the user foreign key cascades. Downgrade drops only this content-free
authority table; upgrading again starts with no trusted refresh sessions and requires login.

The vault-lifecycle revision follows the refresh-session head. It adds the two owner fields with a
`ready`/`NULL` backfill, state/fingerprint check constraints and an index over lifecycle state.
Upgrade preserves all vault records. Downgrade refuses while any owner is pending because dropping
the recovery marker could expose a partially reset, restored or erased vault as normal; once every
owner is `ready`, downgrade removes only the index, checks and lifecycle columns.

The provider-configuration revision follows the dossier-draft and vault-lifecycle chain. It creates
an empty `job_provider_configurations` table with owner/key uniqueness, revision and adapter checks,
plus owner and owner/enabled indexes. It does not infer provider consent or migrate executable
scraper logic. Downgrade drops only these declarations; already captured jobs remain intact.
