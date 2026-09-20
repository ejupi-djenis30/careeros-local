# Historical Implementation Restart — Feature 002

Closed 2026-09-13, Europe/Zurich. This document preserves the handoff used after provider quota
exhaustion; it is no longer the current execution state. All original and appended correction
tasks were subsequently implemented and independently reviewed. Current evidence is in
`analysis.md`, `convergence.md`, `tasks.md` and `validation.md`.

## Authority and handoff state

The owner's goal remains the full MCP opportunity-to-application workflow, nine CV/letter
presets and reviewed reuse of Career-style sources. On 2026-09-13 the owner explicitly authorized
the coordinating Codex agent and its subagents to implement directly after the delegated engines
exhausted their quotas. The coordinator retains specifications, integration review and full
verification. Do not shrink the scope.

Work is uncommitted on `codex/002-mcp-career-workspace`. Preserve all partial changes; no staging,
commit, push, PR or release is authorized. Do not run the partial app on the real vault or alter
`../Career`. Use fictional fixtures and OS temporary directories for outputs, caches and databases.

All implementation processes stopped after provider quota exhaustion. The latest exact Spark
probe at about 12:33 local failed again; provider reset estimate was 16:21 on 2026-09-13.
Antigravity Gemini estimates were about16:38; Claude/GPT-OSS about17:03. These are estimates,
not proof of later availability. Probe the chosen authorized engine once when resuming and
read its actual result before dispatch. No code repair is assumed to have happened during review.
An additional Gemini3.7 Flash probe at12:34 returned repeated quota429 errors and shut down after
its print timeout. The goal was marked blocked after the third consecutive quota-blocked turn,
then resumed when the owner authorized direct implementation. Retain all outstanding tasks and
review obligations.

## Read before editing

1. AGENTS.md and `.specify/memory/constitution.md`.
2. `spec.md`, `plan.md`, `data-model.md` and all three `contracts/*.md`.
3. `tasks.md`, `review-findings.md`, `validation.md` and `analysis.md`.

Only T001-T004 are checked. T055-T066 are additional repair obligations, not replacements for
unchecked original tasks. Review includes R001-R042, RT001-RT016, RR001-RR009 and RA000-RA014.
Recheck each finding against current code before fixing; never weaken a validator or substitute
mock-only evidence to make an acceptance criterion appear complete.

## Dependency order and write ownership

Start with the application worker alone for T055: repair real public imports, exception identity,
profile-based CV ownership and the missing snapshot-sanitizer argument. Preserve public service
behavior rather than adding dummy aliases. Run real app import/pytest collection under isolated
settings and application characterization. No integrated backend story is testable before this.

After bootstrap, assign at most three disjoint implementation slices alongside coordinator review:

| Slice | Exclusive paths | Required first result |
| --- | --- | --- |
| Agent backend | backend/agent_work, backend/automation, agent owner/bridge routes, desktop/session.py and their tests | Strict wire schemas, bounded scoped context/transport, real revision/CAS/expiry/grounding and safe errors; T056-T057 |
| CV/template | backend/resumes, resume route/service/UI and their tests | Nine validated presets, preserved manual evidence/content, three working layouts and actual PDF/DOCX publication; T060 |
| Application | backend/applications, application routes/UI/service and their tests | Shared flush-only transaction seam, approved CV binding, immutable packet/journal integrity, letter/email artifacts; T065 and T061 |

Do not concurrently edit shared locale files, migrations, model registration, API registration or
test setup. The coordinator assigns their ownership explicitly. Current migration chain is
old head -> b0c1d2e3f4a5 -> b1c2d3e4f5a6 -> b2c3d4e5f6a7 -> b3c4d5e6f7a9; inspect actual
heads before adding/changing migrations. A similar revision ending a8 already existed historically.

Once the application and CV mutation APIs are reviewed, hand their exact signatures/transaction
contract to the agent worker for strict material DTOs and atomic material acceptance (T036-T037).
Do not let materials transition to accepted until the intended CV/dossier draft writes succeed.

Use freed slots for reference import T062/T066 (backend/career, career route/service/UI/tests),
agent UI T059 (agent-work/access, job projections/navigation and corresponding tests), and installed
bridge T063 (desktop lifecycle/descriptor, packaging scripts, native command/tests). Agent UI
must use real serialized DTOs. Native worker must coordinate changes to mcp_server.py and
desktop_client.py with the agent owner; those files cannot have simultaneous writers.

T058 portability/reset/erasure follows stabilized schemas and packet storage. It is mandatory:
the current archive format does not include all new records/files. Assign one owner to migration,
archive/restore/journal/reset integration. Preserve legacy packet bytes, bound paths, canceled
restored work, nulled grant authority, historical snapshots and owned relationship remapping.

## Required regression evidence

- Real migrated file SQLite and two independent sessions for stale/CAS/terminal races, including
  dossier draft writes. Outer material acceptance owns commit and rollback; no hidden commits,
  rollback or swallowed partial failure inside a purported flush-only domain seam.
- Inject failure before commit, ambiguous commit acknowledgement and journal cleanup after
  successful commit. A committed packet remains downloadable; failed cleanup retains recovery
  evidence. Reconcile under the vault lock without deleting another bound artifact.
- Schema 1/2 byte-stable reconstruction and schema 3 stored-byte integrity. Missing schema 3
  metadata/bytes fails explicitly. Validate selected CV/draft correspondence, its readiness and
  full saved letter/email/provenance equality; preserve route error identities.
- Letter PDF must have readable pages and all approved text/contacts; build once. Escape all
  input fragments, assert no supplied resource tag causes filesystem/network access. Validate
  complete mailbox/header/control/attachment grammar against exact generated EML/checklist names.
- Deferred UI responses for save -> accept new preference -> old save response, and upload A ->
  choose B -> old A response. Validate 50+1 merged roles, conflicting scalar choices, 51 review
  notes, whole numeric syntax and explanatory omissions. Fix the existing checkbox test selector
  by accessible identity while keeping its behavior assertion.
- Actual SDK tool schemas/stdio/desktop lease, real no-model guards, grant scope/expiry/revocation,
  path/host/origin/peer checks, byte caps, total deadlines and content-free failure outputs.
- All nine presets through saved draft publication/restore, complete visible text, genuine
  diacritics, nested/merged tables, A4 on every page/section, safe actual hyperlinks and photo
  round trips. Inspect rendered images for each layout and paired letter, not only text extraction.

Current global test setup bypasses local-model readiness and shares a StaticPool connection;
those fixtures alone cannot prove real no-model behavior or independent-connection concurrency.
AST/handler probes documented in review findings are diagnoses, not replacements for new tests.

## Final verification and closure

Use the repository `.venv` (Python3.12.13 x64); global Python3.14 is unsupported. Initialize
settings against OS-temp paths before importing app/tests. Remove temporary DATA_DIR/DATABASE_URL
environment overrides before tests constructing fresh Settings; preserve isolated singleton fields.
Keep pytest basetemp/cache/junit under OS temp. Final normal suite and concurrency fixtures need
their intended separate SQLite environments. See validation.md for the baseline isolation issue.

Run proportionate slice tests first, then every full backend/frontend/native gate, populated
migration upgrade/downgrade/re-upgrade, portability/erase/rollback, offline golden evaluations and
the complete real-backend browser discovery -> analysis -> reviewed materials -> readable unsent
packet journey. Record exact failures/skips. At handoff, ARM64 native runtime packaging was unverified;
x64 Python or disabling Tauri resource checks is not evidence of a supported ARM64 package.

Diagnostics at handoff: Ruff36 errors, Mypy12 errors, pytest bootstrap failure with zero tests;
frontend556 passed/1 failed, lint1 error, build passed. Empty migration cycle passed only.
Six trailing-blank-line errors remained in delegated files from `git diff --check`. They required
authorized fixes; the final evidence superseding this snapshot is linked at the top.

After each slice, coordinator reviews actual code and evidence and returns defects to the
authorized engine. Complete docs, independent Spec Kit analysis and convergence only after all
story acceptance and required checks are satisfied. Mark the goal complete only then.

## Earlier Antigravity conversation handles

These may help resume preserved context; current spec/review files take precedence over old logs.

| Slice | Conversation |
| --- | --- |
| Agent backend | cb81c23d-2b7f-4f2c-9f0b-ab50a3e980e4 |
| Template studio | ffa5a26b-0c0f-4189-a198-3a69fd429afc |
| Agent UI | 53ffd8c4-5c99-4394-a1fe-318807e09022 |
| Reference import | 6c0191e6-64bc-40c9-91c0-e49668402249 |
| Application packets | 81e20f54-8a41-4575-a7d4-a1eeff5c466b |

Prior prompts/logs are under OS temp `careeros-agy-*` directories. The installed bridge worker
was interrupted while reading and made no implementation; do not assume that slice exists.
