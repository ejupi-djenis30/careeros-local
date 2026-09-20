# Feature Specification: Legacy Campaign Workspace

**Feature branch**: `codex/003-campaign-workspace`
**Status**: Approved for implementation
**Owner workflow**: Codex specifies and verifies; Antigravity CLI using Gemini 3.8 Flash implements.
**Constitution**: CareerOS Local Constitution 2.0.1

## Problem and audited baseline

The current CareerOS vault can manage applications, tasks, evidence, resumes and dossier drafts,
but it cannot ingest the existing local campaign as one coherent, reviewable workspace. The
audited campaign contains:

- 176 unique tracker rows across 28 columns;
- 123 dossier directories, of which 122 match tracker identifiers and one exists only as a dossier;
- 54 tracker records with no dossier directory;
- 177 logical applications after reconciliation;
- 906 allowlisted files (95,222,414 bytes) across the tracker, root profile/goal/story/diploma
  references, assets, application packets, templates and scripts;
- a `Platform Credentials` worksheet with 3 non-empty data rows, all of which are excluded by
  policy without materializing or exposing their values.

These counts are release evidence, not fixture content. Automated tests MUST use fictional data.

## User outcomes

### US1 — Preview and import the complete campaign (P1)

As the vault owner, I select one local ZIP assembled from the campaign workspace and receive a
read-only preview before any mutation. The preview identifies the archive fingerprint, tracker
records, matched/tracker-only/dossier-only applications, artifacts, status distribution, omitted
credentials and warnings. I can then explicitly confirm an import bound to that fingerprint.

Acceptance scenarios:

1. A valid fictional archive previews without changing any database row or managed asset.
2. Committing the unchanged archive creates exactly one campaign and one logical application per
   reconciled source identifier, stores every allowlisted artifact, and reports deterministic
   counts.
3. Re-importing the same fingerprint for the same account returns the existing campaign without
   duplicating applications, events, tasks, sources or bytes.
4. A changed archive cannot be committed with an older preview fingerprint.
5. The `Platform Credentials` sheet is never returned or persisted; a non-empty sheet produces
   only a content-free omission warning and count.
6. Traversal, absolute paths, duplicate canonical names, symlinks, encryption, excessive members,
   oversized files and unsupported top-level roots fail before writes.

### US2 — Operate every application from CareerOS (P1)

As the vault owner, I can search and filter imported applications, inspect their original tracker
metadata and materials, then use the existing CareerOS application workflow to manage stage,
events, next action, tasks, dossier draft, cover letter, email draft, exports and confirmation of
an externally submitted application.

Acceptance scenarios:

1. Imported cards are searchable by source ID, title, company, platform and category and filterable
   by stage and priority.
2. The detail view shows source status, priority, dates, platform/source, URLs, contacts,
   submission fields, outcome, next action and notes exactly as imported, without treating them as
   confirmed profile facts.
3. Packet files are grouped by category and downloaded only through an authenticated,
   account-scoped attachment response with `nosniff`; HTML, scripts and email files are never
   executed or rendered as active content.
4. Active tracker rows receive a pending task only when a next action exists; closed rows do not
   create active work. Existing application controls continue to append immutable events.
5. `Closed` maps conservatively to `archived`; it is never guessed to mean rejected. Original
   status and outcome remain verbatim in campaign metadata.
6. The dossier-only record is represented as a `preparing` application using only fields parsed
   deterministically from its vacancy reference; unknown values stay unknown.

### US3 — Reuse campaign knowledge and templates (P2)

As the vault owner, I can inspect the root profile, goal, storytelling, diploma and template
references in the campaign and use them in CareerOS preparation workflows without silently
confirming claims.

Acceptance scenarios:

1. Compatible root references are imported as reviewable source documents with explicit roles;
   candidate facts and preferences remain unconfirmed until the owner accepts them.
2. Historical CVs, letters, emails and generated documents remain evidence artifacts and are not
   misrepresented as verified CareerOS resume versions.
3. The user can generate new CareerOS-native resume/dossier materials from confirmed facts, while
   retaining access to the historical references used in the campaign.
4. If the account has no candidate profile, import requires an explicit display name (prefilled
   from a deterministic local suggestion when available) before creating the minimal profile.

### US4 — Preserve ownership, portability and recovery (P1)

As the vault owner, imported campaign records and bytes behave like first-class vault data.

Acceptance scenarios:

1. Portable archive version 8 exports, inspects and restores campaigns, links and assets with
   relational and digest validation.
2. Reset, complete erasure and account deletion remove campaign rows and exclusively owned files;
   shared content-addressed files are preserved while referenced.
3. Upgrade and downgrade are tested. Downgrade refuses when campaign rows exist rather than
   destroying imported data silently.
4. No import path bypasses the desktop-owned vault lease or opens a second writable database.

## Functional requirements

- **FR-001** Accept a user-selected ZIP only; never crawl an arbitrary directory from the backend.
- **FR-002** Support one optional common archive prefix and these top-level inputs only:
  `ApplicationTracker.xlsx`, root `Profile.md`, `Goal.md`, `Storytelling.md`, root PDF references,
  `assets/`, `application-packets/`, `cv-templates/`, `cover-letter-templates/`,
  `email-templates/`, `html-templates/`, and `scripts/`.
- **FR-003** Exclude `outputs/`, `backups/`, `tmp/`, `careeros-local/`, credentials and every
  unrecognized top-level member.
- **FR-004** Enforce at most 5,000 members, 128 MiB compressed, 256 MiB expanded and 10 MiB per
  file. Reject encrypted entries, symlinks, special files, traversal, backslashes, drive/UNC paths,
  empty canonical paths and case-insensitive canonical duplicates.
- **FR-005** Parse XLSX with Python standard-library ZIP/XML facilities. Do not add a spreadsheet
  runtime dependency solely for import. Before XML parsing, apply a second package boundary of at
  most 100 XLSX members, 32 MiB expanded and 10 MiB per member, with the same encryption, special
  file, canonical-path and duplicate-name rejection rules as the outer archive.
- **FR-006** Read the `Applications` table by its header row, preserve all 28 source fields, support
  shared/inline strings and Excel dates, and reject duplicate/missing source application IDs. The
  typed projection must recognize the audited headings `Date Found`, `Application Date`,
  `Platform / Source`, `Platform URL`, `Job Posting URL`, `Follow-up Date`, and `Last Update`
  without renaming or losing the verbatim tracker record.
- **FR-007** Inspect `Platform Credentials` only to count non-empty data rows; never materialize or
  echo cell values. The original tracker XLSX must never be persisted because it contains that
  worksheet and credential-bearing shared strings. Import stores one deterministic, valid,
  credentials-free tracker derivative containing only the 28 `Applications` fields; this replaces
  the tracker artifact while preserving the 906-artifact logical count. `tracker_sha256` may retain
  only the one-way digest of the original member.
- **FR-008** Compute a canonical SHA-256 fingerprint from normalized path, byte length and member
  digest, independent of ZIP entry order and timestamps.
- **FR-009** Preview is side-effect free and returns only bounded samples plus aggregate counts.
- **FR-010** Import requires the expected preview fingerprint and is atomic: rows and publication
  journal either converge completely or roll back/recover.
- **FR-011** Store source bytes via `CareerAsset`; add inert `campaign_document` publication kind
  under `assets/campaign/{sha-prefix}/{sha}` and retain source media type, size and digest.
- **FR-012** Reconcile by source application ID. Match a packet directory exactly first, then by
  the longest tracker ID followed by `_` when the directory carries a descriptive suffix; reject
  ambiguous duplicate resolutions. Tracker data wins structured metadata, the complete directory
  name remains provenance, dossier materials attach to the match, and dossier-only records use
  deterministic `vacancy.md` parsing.
- **FR-013** Create manual Job/Application records under the authenticated user and immutable
  application events consistent with the mapped stage and available source dates.
- **FR-014** Map `Saved→saved`, `Preparing→preparing`, `Applied→applied`, `Closed→archived`.
- **FR-015** Never send applications, email contacts, publish documents, confirm facts or approve
  agent proposals during import.
- **FR-016** Expose campaign list/detail, application campaign context and account-scoped artifact
  download endpoints under `/api/v1`.
- **FR-017** Add an Applications-page import panel, preview/confirm flow, text search, stage and
  priority filters, campaign metadata, grouped artifact downloads and localized English/Italian
  labels.
- **FR-018** Native desktop file selection reads one ZIP through the existing explicit-dialog
  boundary; browser fallback uses a file input. Neither path persists the selected path.
- **FR-019** Include campaign entities in portability v8, reset, erasure, deletion, model registry
  and empty-vault assertions.
- **FR-020** Keep route handlers thin, modules under 300 lines and React components under 150 lines
  unless a documented plan exception is added before implementation.

## Non-functional requirements

- No campaign content, contact data, filenames containing personal data, workbook cells or file
  bytes may enter logs, error telemetry or test snapshots.
- Import must remain usable without a local model and without network access.
- Preview and import results must be deterministic for identical bytes.
- UI must remain keyboard accessible and disclose that ZIP input is unencrypted and local.
- Existing application, portability, source-document and dossier behavior must remain compatible.

## Out of scope

- Sending applications or email on the user's behalf.
- Running imported scripts or HTML.
- Treating historical PDFs as editable CareerOS resume versions.
- Importing passwords, tokens or platform credentials.
- Cloud synchronization or provider-specific inference inside CareerOS.

## Release success criteria

1. All synthetic unit, contract, integration and frontend tests pass with network denied.
2. Migration empty→head, prior→head and head→prior→head (with no campaign data) pass; downgrade
   with campaign data refuses clearly.
3. A disposable-vault import of the real campaign reports 177 logical applications, 176 tracker
   rows, 123 dossiers, 122 matches, 54 tracker-only, one dossier-only and 906 artifacts.
4. A second real import is a no-op by fingerprint and produces identical counts.
5. Export/inspect/restore of that disposable vault retains the campaign counts and artifact
   digests; complete erasure leaves no campaign rows or exclusively owned campaign bytes.
6. Full backend, frontend and Rust gates defined in `AGENTS.md` pass.
