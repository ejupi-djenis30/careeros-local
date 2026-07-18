# Data Model: CareerOS Local Desktop Career Agent

## Persistence boundaries

- The career vault is the canonical SQLite database under the OS application-data directory.
- Attachments, photos, resume artifacts, models and runtime binaries are content-addressed or
  integrity-manifested files beside the database, never database blobs.
- Session tokens, ports, process identifiers and active download progress are ephemeral and
  MUST NOT be written to the vault.
- Prompts and model outputs are never stored in AI audit tables; trusted product records store
  only the accepted domain result already required by the user workflow.

## Existing entities retained

### Career Vault

Aggregate over users, candidate profile, career facts, evidence sources, assets, goals, jobs,
applications, workflows, coach conversations, resume drafts, immutable versions and exports.
Backup manifests include schema version, record counts and content hashes.

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

