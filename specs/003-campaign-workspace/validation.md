# Validation matrix

## Pre-implementation baseline — 2026-09-19

- Ruff: passed.
- Mypy (`backend`): passed with no diagnostics.
- Backend Pytest: 2,613 passed, 23 skipped; one non-product warning because the sandbox denied
  creation of `.pytest_cache`; duration 842.06 seconds.
- Frontend test suite: 88 files / 602 Vitest tests passed; Node contract, license and icon subset
  checks passed.
- `git diff --check`: passed before feature implementation.

## Synthetic automated evidence

| Area | Required evidence |
|---|---|
| Archive safety | traversal, absolute/UNC, backslash, duplicate canonical name, symlink, encrypted, size/member/expanded limits rejected pre-write |
| XLSX | shared/inline text, styles/dates, 28 headers, duplicate IDs, missing IDs, selective shared-string privacy, empty/non-empty credentials omission, nested-package limits/path attacks |
| Preview | zero DB/file mutations; stable fingerprint/counts independent of ZIP order/timestamps |
| Import | atomic success/rollback, exact reconciliation, conservative stages/events/tasks, root sources pending review; stored tracker derivative contains no credential sentinel or credential worksheet/shared strings |
| Idempotence | same user+fingerprint returns existing campaign; changed/stale fingerprint conflicts |
| Ownership | cross-user campaign, context and artifact access denied without existence leakage |
| Downloads | verified digest/length/path; attachment, nosniff, no-store; no active rendering |
| Portability | v8 export/inspect/restore; v1–7 compatibility; FK/digest/path tampering denied |
| Lifecycle | reset/erasure/deletion remove rows; shared bytes retained; exclusive bytes removed |
| UI | import preview/confirm, profile bootstrap, filters, error recovery, EN/IT, keyboard labels |

## Phase 1 parser/preview evidence — 2026-09-19

- Independent campaign parser/preview suite: 60 passed.
- Ruff on `backend/campaigns` and `tests/backend/campaigns`: passed.
- Mypy on `backend`: passed with no diagnostics.
- The real tracker was read without persistence and produced exactly 176 rows, 28 raw headers and
  3 omitted credential rows.
- Real typed projections matched the audit oracle: `Date Found` 147, `Application Date` 77,
  `Platform / Source` 176, `Platform URL` 147, `Job Posting URL` 147, `Follow-up Date` 40,
  `Last Update` 176 and preferred URL 147.
- No personal field values or credential contents were printed during validation.

## Phase 2A persistence/journal evidence — 2026-09-19

- Independent campaign backend suite: 75 passed in 14.08 seconds.
- Ruff on campaign models/tests, the migration, model registry and asset publication: passed.
- Mypy on `backend`: passed with no diagnostics.
- Alembic reports the campaign revision `c0a1b2c3d4e5` as the single head; the focused migration
  suite covers disposable prior→head, empty head→prior→head and refusal of downgrade while campaign
  rows exist.
- Independent review confirmed parity between ORM and migration index names, campaign/application/
  artifact uniqueness, all declared `ondelete` policies, the fail-closed artifact category check and
  the UTC `CampaignArtifact.created_at` default.
- `campaign_document` publication uses `assets/campaign/{sha256[0:2]}/{sha256}` and focused crash
  recovery tests preserve committed bytes, remove uncommitted bytes and leave existing publication
  kinds unchanged.
- `git diff --check`: passed.

## Phase 2B1 immutable parse/sanitized-tracker evidence — 2026-09-19

- Independent campaign backend suite: 88 passed in 14.96 seconds.
- Ruff on campaign code/tests, the migration, model registry and asset publication: passed.
- Mypy on `backend`: passed with no diagnostics; `git diff --check` passed.
- Review confirmed that parsed headers, rows, applications, artifacts, warnings, archive members,
  status counts, tracker records and nested provenance sources are transitively immutable.
- A read-only round trip of the real tracker preserved all 176 Applications rows and all 28 ordered
  headers exactly while reducing credential rows from 3 to 0. The deterministic derivative contains
  six package members, no shared-strings member and no credential-named member.
- Focused fictional tests cover boolean, integer, finite-float, date, null and whitespace-preserving
  string round trips; non-finite floats fail closed and leading/trailing whitespace uses
  `xml:space="preserve"`.
- No personal field values or credential contents were printed during validation.

## Phase 2B2 conservative import-plan evidence — 2026-09-19

- Independent campaign backend suite: 102 passed in 15.57 seconds before the boundary-test
  correction; the focused planner suite then passed 14 tests after explicit exact-limit coverage.
- Ruff on the planner and its tests passed; mypy on `backend` passed with no diagnostics; and
  `git diff --check` passed.
- Focused tests prove the required Saved, Preparing, Applied and both Closed paths; strictly
  increasing, import-bounded UTC event instants; tracker-only active-task creation; closed and
  dossier-only task absence; deterministic IDs and revisions; and transitive plan immutability.
- Snapshot tests prove vacancy-first descriptions with safe fallback, conservative URL and email
  omission, whitespace-only title/company fallbacks, and no unsafe optional keys.
- Preflight tests prove each persisted string field accepts its exact database maximum and rejects
  `max + 1` without echoing source values; artifact categories must be in the fail-closed domain.

## Phase 2C atomic import evidence — 2026-09-19

- Independent focused import suite: 25 passed in 12.95 seconds; independent complete campaign
  backend suite: 128 passed in 30.57 seconds.
- The suite proves one-commit creation, zero-commit idempotent replay at a later request time,
  stale-fingerprint refusal, exact owner-scoped graph verification, pre-commit rollback, and both
  successful and fail-closed recovery after an uncertain commit result.
- Corruption coverage changes campaign metadata/summary, application projection/ownership,
  campaign links, event identity/data, artifact bindings, asset metadata/bytes and root source
  documents; every retry returns a bounded conflict without writing.
- Cross-user and duplicate-content tests prove owner-scoped row identities, per-profile
  `CareerAsset` rows, safe reuse of content-addressed bytes, and cleanup that preserves every
  still-referenced shared file.
- Compatible root references are prepared before writes and persisted only as reviewable
  `SourceDocument` rows with explicit roles; no facts, goals or preferences are confirmed.
- Every production module under `backend/campaigns` is below 300 physical lines. `ruff check .`,
  mypy on all 337 backend source files and `git diff --check` passed.

## Phase 3A authenticated API evidence — 2026-09-19

- Independent campaign backend suite: 139 passed in 41.49 seconds; the focused HTTP contract suite
  contributed 11 passing tests. The only warning was the known sandbox denial for `.pytest_cache`.
- Contract coverage proves authenticated preview is side-effect free, malformed/semantic/oversized
  inputs receive bounded generic errors, import returns 201 then an idempotent 200, stale previews
  write nothing, and list/detail/search/filter/pagination expose only bounded owner-scoped data.
- Application summaries expose nullable campaign projections; context responses preserve inert
  tracker/provenance data and grouped artifact metadata; unowned and missing resources return the
  same 404 shape without identifiers or existence leakage.
- Artifact downloads verify owner, content-addressed path, digest and byte length before returning
  any bytes, force attachment plus `nosniff`/`no-store`, and fail closed on corruption.
- Exact pre-parser body limits cover both multipart routes. The new route and API-service modules are
  182 and 209 physical lines respectively; all campaign production modules remain below 300 lines.
- Focused Ruff passed, mypy passed across all 339 backend source files, and `git diff --check` passed.

## Phase 3B local campaign UI evidence — 2026-09-19

- Independent focused Vitest run: 7 files / 44 tests passed, covering multipart service calls,
  native and browser ZIP selection, aggregate-only preview, profile bootstrap, bounded retries,
  campaign/stage/priority/search filters, inert grouped materials and authenticated downloads.
- Independent complete frontend suite: 92 Vitest files / 616 tests passed; the Node runtime,
  dependency-license, distribution and icon-subset contracts also passed.
- English and Italian catalogues retain exact key/interpolation parity. Priority and all canonical
  material-category labels are localized, while preview and error paths do not expose source
  filenames, native paths or exception details.
- `npm run lint`, `npm run build` and `git diff --check` passed. The production build transformed
  255 modules and remained within every configured raw/gzip bundle budget.
- The four new campaign UI components are each below 150 physical lines; imported tracker content
  is rendered only as inert React text and no campaign path or private error value is interpolated.

## Phase 4 portability and lifecycle evidence — 2026-09-19

- Independent combined portability/campaign run: 319 passed in 186.89 seconds (180 portability,
  including 34 focused v8 campaign tests, plus 139 campaign tests).
- Portable format v8 includes campaign, campaign-application and campaign-artifact records while
  preserving the exact historical v1–v7 table sets. Export, inspection and restore validate
  ownership, references, digests, canonical managed paths, aggregate summaries and source order.
- Twenty-four focused tampering cases reject malformed provenance, non-canonical source sequences,
  invalid dossier directory provenance, nested tracker data, aggregate/count changes, order gaps,
  display-name divergence and NFC/casefold path collisions before any restore write.
- Lifecycle coverage proves reset and complete erasure remove campaign rows and exclusively owned
  bytes while retaining content-addressed bytes still referenced by another profile. Empty-scope
  restore conflicts and account-scoped ownership remain fail closed.
- Migration coverage exercises prior→head, empty head→prior→head and explicit refusal of downgrade
  when any campaign table contains rows, without destructive data loss.
- Focused Ruff passed; mypy passed across 340 backend source files; `git diff --check` passed. The
  v8 campaign validator remains 294 physical lines, below the 300-line constitution limit.

## Real campaign aggregate oracle

The source directory is never committed or copied into fixtures. On a disposable vault, the local
archive built from the audited workspace must produce:

| Metric | Expected |
|---|---:|
| tracker rows | 176 |
| dossier directories | 123 |
| tracker/dossier matches | 122 |
| tracker-only records | 54 |
| dossier-only records | 1 |
| logical applications | 177 |
| imported allowlisted artifacts | 906 |
| input bytes | 95,222,414 |
| credential rows omitted | 3 |
| credentials imported | 0 |

The status distribution from the tracker is Applied 78, Closed 85, Saved 5 and Preparing 8.
Nineteen of the 122 matched dossier directories append an underscore plus descriptive slug to the
tracker ID; reconciliation must normalize those directories without changing their provenance.
Typed-projection aggregate checks are: 147 non-empty `Date Found` values, 77 non-empty
`Application Date` values, 176 non-empty `Platform / Source` values, 147 non-empty `Platform URL`
values, 147 non-empty `Job Posting URL` values, 40 non-empty `Follow-up Date` values, and 176
non-empty `Last Update` values.
The validation output may print these aggregates, IDs only when necessary for reconciliation, and
digests; it must not print companies, people, contacts, notes or document bodies.

## Phase 5 migration utility evidence — 2026-09-20

- `scripts/build_campaign_archive.py` and its library use the same top-level allowlist as the
  parser, reject links/reparse points, unsafe canonical names, collisions and all configured
  boundaries, and publish no partial output after a failure.
- Repeated builds over identical bytes are byte-for-byte deterministic: member ordering, ZIP
  timestamps, modes, comments, extras and compression behavior are fixed. The builder's success
  report contains only counts, byte totals and digests.
- `backend/campaigns/aggregate_validation.py` is read-only and emits a fixed aggregate schema. It
  never returns path names, source IDs, companies, people, contacts, notes, warnings copied from
  source content or document bodies.
- Fictional regression tests cover inclusion/exclusion, deterministic builds, traversal,
  Unicode/casefold collisions, link-like inputs, exact limits, changed-during-read files, generic
  errors, aggregate-schema privacy and order/timestamp independence.
- Both production modules remain within the constitutional 300-physical-line budget. The utility
  adds no network, hosted AI, telemetry or runtime spreadsheet dependency.

## Real campaign end-to-end proof — 2026-09-20

The proof used a clean temporary database, vault and source archive outside the repository. It
completed the builder, aggregate validation, first import, idempotent replay, portable v8 export
and inspection, reset, restore, re-export comparison and complete erasure. It also rebuilt the
source archive and verified that the source was unchanged.

Observed release evidence:

| Check | Result |
|---|---:|
| campaigns after first import | 1 |
| campaign/application links | 177 |
| campaign artifact rows | 906 |
| managed physical files | 902 |
| direct packet-root files kept campaign-level | 2 |
| credential rows omitted / persisted | 3 / 0 |
| second import created a campaign | false |
| portable format | 8 |
| restore reproduced payload/files | true |
| reset and erasure complete | true |
| source unchanged | true |

Non-sensitive SHA-256 commitments from that run:

- source archive: `11a093c028e8290dba7d56bcc8ce468c4887a2acf8ff9a498945f85a8574dab0`
- normalized source members: `93eba5b231af2513e69f8e7c830085972cf07e3daa5ca43f5bd983ac49c6ae56`
- portable payload: `b90290b2cb53ecdba4ff5661cf95c730c4d4bc812648bd317c8abf2410933a47`
- restored managed files: `bb40a2f206f9b5a111b498c918ddda367fdf0c80ca024da9aeb7e20e088545d8`

The real proof and final read-only audit exposed five boundary cases and each received a synthetic
regression before the final replay: direct packet-root files must remain campaign-level; a full
campaign platform/source value may exceed the 40-character job snapshot projection; tracker
strings from 4,001 through 32,767 characters are valid XLSX values and must not be truncated;
single allowlisted root directories are not wrapper prefixes; and numeric/boolean cells in textual
columns need safe string projections while the raw primitive remains unchanged. Focused post-fix
tests passed, including acceptance at 32,767 and rejection at 32,768 characters before persistence.

## Final read-only audit — 2026-09-20

- Luna inspected privacy/error boundaries, transaction recovery, ownership, XSS/inert downloads,
  path/symlink/Unicode handling, v1-v8 compatibility, lifecycle, migration behavior, network/AI/
  telemetry absence and line budgets without modifying files or reading external directories.
- The first pass found the single-root prefix bug and the missing import-time XLSX cell limit, plus
  the numeric typed-field hazard. Codex added failing fictional regressions and Antigravity applied
  the production fixes.
- The second pass reproduced the fixed boundary cases and reported no remaining blocker. Its
  focused audit run passed 70 archive/planner/XLSX tests plus the 32,767-character v8 round trip.
- All campaign production modules and `backend/portability/campaigns.py` remain below 300 physical
  lines; all new React campaign components remain below 150.

## Final release gates — 2026-09-20

- Final boundary regressions: 6 passed, covering the two single-root variants, wrapper stripping,
  import-time XLSX cell limit, numeric/boolean textual projections and verbatim nonblank strings.
- Complete campaign backend suite: 165 passed in 58.81 seconds.
- Complete portability backend suite: 186 passed in 208.48 seconds.
- Complete backend suite on the final tree: 2,786 passed, 17 skipped and one warning in 1,238.82
  seconds. The only warning was the known local Windows denial when Pytest attempted to create
  `.pytest_cache`; no product test warned or failed.
- `ruff check backend tests/backend`: passed. Mypy on `backend` completed with exit code zero and no
  diagnostics. Final `git diff --check`: passed.
- Complete frontend suite: 92 Vitest files / 616 tests passed together with the Node contract,
  dependency-license, distribution and icon-subset checks. `npm run lint` and `npm run build`
  passed; the build transformed 255 modules within all configured budgets.
- `cargo fmt --check`, Clippy for all targets/features with warnings denied, and Rust tests for all
  targets/features passed.
- Alembic empty→head, head→previous→head and prior→head passed on disposable databases. Downgrade
  with campaign rows refused without data loss, as designed.
- The final real campaign proof passed after the boundary fixes, and the sensitive temporary proof
  directory was removed after the evidence below was recorded.

## Required gate commands

Use repository-supported environments discovered during implementation. At minimum:

```text
ruff check .
mypy backend
pytest
npm test
npm run lint
npm run build
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --all-targets --all-features
```

Also run Alembic empty→head, prior→head, head→prior→head without campaign rows, and verify that a
downgrade with campaign rows refuses without data loss.
