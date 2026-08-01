# Changelog

All notable changes to CareerOS Local are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [Unreleased]

## [1.11.1] - 2026-08-01

### Fixed

- Concurrent identical content-addressed writes now accept the narrowly scoped POSIX `ctime`
  transition caused when the winning publisher removes its private hard-link alias. Descriptor,
  inode, file type, exact size, modification time and content still have to match, while recovery
  metadata retains its stricter single-link and `ctime` invariants.

### Changed

- v1.11.1 is the first published 1.11 distribution and carries every addition, change and fix
  recorded in the v1.11.0 candidate section, including restart-durable vault and migration
  recovery, bounded private-file journals, hardened local runtimes, content-free diagnostics,
  accessibility coverage and the schema-4 26-asset release contract.
- The signed v1.11.0 source tag remains immutable, but its publication was stopped before a GitHub
  Release or any public release asset was created.

## [1.11.0] - 2026-08-01

### Added

- Added restart-durable Career Vault reset, restore and erasure recovery with four persisted
  lifecycle states, a checksummed restore journal, purpose-bound maintenance sessions and a
  same-archive retry flow.
- Added a closed, typed diagnostics and activity registry for search progress, failure codes and
  public status messages. Persisted search diagnostics now use schema v2 and discard legacy,
  malformed or tampered entries instead of replaying untrusted text.
- Added real forced-colors, keyboard-focus and WCAG checks for login and Agent Access across the
  supported English and Italian responsive layouts.
- Added container lifecycle CI for migrations, health, registration, login, authenticated
  mutation, restart persistence and graceful shutdown, plus an exact expiring Ollama
  vulnerability baseline that distinguishes 31 findings across 30 vulnerability identifiers.
- Added one canonical packaged Alembic chain, a bounded cross-process migration lock and a
  checksummed recovery journal that restores the previous SQLite vault after an interrupted or
  failed schema upgrade.
- Added strict restart journals for source, photo, resume-artifact and portable-restore publication;
  every journal has an explicit entry/path/byte ceiling and is read through a stable regular-file
  descriptor before recovery can change private state.
- Added one bounded canonical installation-secret reader for container fallback, CLI and MCP
  startup, including regular-file identity, link/reparse, private-path, POSIX ownership/mode and
  pre/post descriptor checks.

### Changed

- The contributor backend image now uses the digest-pinned Python 3.12.13 Alpine 3.23 runtime on
  amd64 and arm64, runs as UID/GID 10001 and removes pip, ensurepip, setuptools and idle from the
  production surface.
- The Compose stack now pins Ollama 0.32.0, separates application and model traffic, bounds process
  counts and log retention, and applies read-only roots, temporary writable storage, dropped
  capabilities and no-new-privileges consistently.
- Runtime contracts now pin CPython 3.12.13 for backend and container work, CPython 3.13.14 for
  cross-platform native sidecars, and Node 24.18.x. Third-party notices are regenerated from
  those exact inputs, include the reviewed native-runtime license, and remain lock-bound before
  acceptance.
- Container access logs now retain only content-free operational timing/status fields, Uvicorn
  access logging is disabled in favor of structured application diagnostics, and web assets stay
  root-owned and non-writable by the Nginx worker.
- Production runtimes no longer expose CDN-backed Swagger/ReDoc pages or the HTTP OpenAPI endpoint;
  development and direct Python contract generation remain available. Credentialed CORS now
  accepts exact configured origins only and no longer exposes a regex expansion option.
- Both runtime images now carry root-owned, non-writable canonical `LICENSE` and
  `THIRD_PARTY_NOTICES.txt` files under the standard system license directory, with byte-for-byte
  digest checks in container CI.
- The authenticated workspace and layered Bootstrap CSS now load only after session restoration.
  Locale catalogues retain all 1,524 bilingual keys in a compact namespace representation, and
  ratcheted login plus authenticated-chunk budgets preserve measured transfer headroom.
- Environment, private API prefix, trusted Host authority, JWT algorithm, production signing
  secret, credentialed CORS origins and renderer API bases now use canonical fail-closed
  configuration contracts, including bracketed IPv6 normalization.
- Provider, local-inference and managed-runtime transports now enforce strict response identity,
  byte and time envelopes before decoding. Source parsing and photo normalization run outside the
  SQLite writer boundary while liveness probes remain responsive.
- Desktop startup now migrates before the first application database handle, validates its private
  data directories and installation secret through stable descriptors, and accepts only an exact,
  bounded JSON readiness response from the loopback sidecar.
- SQLite startup now parses, resolves and contains the target without filesystem mutation, acquires
  the bounded no-follow migration lock, and only then creates the private data chain and reserves a
  new database. It applies and verifies WAL, foreign-key, secure-delete and trusted-schema policies
  before the lazy application engine opens its first handle, and enforces `0700` directories plus
  `0600` main/WAL/SHM/journal files on POSIX.

### Fixed

- The NSIS uninstaller now removes only its per-user location and language metadata after a full
  uninstall, preserves all four MSI-owned registry values even when the user selects delete app
  data, and fails closed before deleting files whenever Windows Installer still owns the shared
  payload. The real installer smoke proves that refusal leaves the application, backend,
  uninstaller and MSI registration intact, then removes the simulated MSI ownership and verifies
  the normal NSIS uninstall and rollback paths without touching the user-owned CareerOS vault.
- Windows sidecar verification now rejects PE machine types that do not match the declared native
  release target.
- Updated the Tauri transitive `event-listener` lock from 5.4.1 to 5.4.2, removing the
  `RUSTSEC-2026-0221` soundness advisory from the complete desktop dependency graph.
- Search status, logs and exception paths no longer persist or emit raw query, provider, profile,
  URL or exception content; forged diagnostic wrappers and arbitrary logging arguments fail
  closed at the public boundary.
- Agent Access and login controls now retain system colors, visible focus, readable status
  boundaries and operable primary actions when Windows forced-colors mode is active.
- Search target queues now expose content-free ordinal labels instead of rendering query, domain
  or provider values in progress UI.
- Every direct and proxied `/api/v1` response is non-cacheable, including early authentication,
  CORS, Trusted Host and exception responses. Browser auth mutations now reject any supplied
  origin outside the exact local UI allowlist, and the obsolete browser XSS auditor is explicitly
  disabled.
- Access tokens without an explicit `access` type now fail closed. Access and refresh tokens now
  belong to a persisted session family: refresh rotation is single-use, replay revokes the family
  and ordinary workspace routes reject purpose-bound maintenance sessions.
- External job, CV and application links now require HTTPS; plain HTTP remains available only for
  exact loopback hosts. Credential-bearing, protocol-relative, non-loopback cleartext and
  ambiguous IPv6/IDN targets fail closed before browser or native navigation.
- Registration and login reject passwords beyond bcrypt's 72-byte UTF-8 boundary without
  truncation or hash work. A failed explicit logout now hides the private workspace, reports that
  the local server session was not ended and offers a retry instead of claiming success.
- Refresh cookies are scoped to `/api/v1/auth`; login, rotation and logout also remove historical
  root-path CareerOS cookies so upgrades cannot retain ambiguous same-name values.
- Authenticated API responses are no longer dynamically compressed. Nginx emits one private cache
  policy for proxied API responses, revalidates the SPA shell and unhashed public assets, and
  applies immutable caching and gzip only to fingerprinted build assets.
- Source, photo and resume artifact publication now uses create-if-absent ownership with durable
  crash recovery. Verified private-file reads require the recorded size, an explicit byte ceiling,
  a stable regular-file identity and a matching SHA-256 digest, and reject symlink/reparse aliases.
  Windows stability checks retain path/descriptor identity while comparing mutation timestamps
  between descriptor snapshots, avoiding false NTFS metadata drift under concurrent load.
- Interrupted atomic-write cleanup no longer uses recursive path traversal: it skips symbolic links
  and Windows junctions, shares one bounded scan across both private namespaces, completes discovery
  before unlinking, and revalidates every parent chain at deletion time.
- Fixed a POSIX migration-lock lifetime hazard by avoiding secondary database descriptor closes in
  the connection hook, and made source/photo recovery converge from committed SQLite references
  after hard process loss or an ambiguous commit result without deleting another profile's bytes.
- Portable restore and complete-vault deletion now verify a fresh locked SQLite postcondition when
  a commit acknowledgement is lost. A committed restore preserves its rows, files and ready
  lifecycle; a committed deletion completes privacy cleanup without restoring staged bytes, while
  failures proven to occur before commit retain rollback and retry behavior. Erasure session
  finalization likewise accepts an ambiguous commit only after proving ready lifecycle, a cleared
  maintenance fingerprint and zero remaining sessions from a fresh snapshot.
- Portable export now enforces the same ZIP member ceiling as restore before reading any private
  file and rechecks the invariant before assembly, preventing a successful but unrestorable backup.
- Portable restore now rejects Boolean, zero and per-table oversized private-file sizes before
  publication, then requires every bound source/photo or resume-artifact member to match its exact
  declared size, digest and canonical storage path.
- Native backup export publishes without replacement, preserves an externally created race winner
  and keeps the recovery file when publication cannot complete; renderer-to-Rust backup payloads
  are capped at the backend's 128 MiB archive limit.

## [1.10.0] - 2026-07-30

### Added

- Agent Access is now available as an installable Python wheel for Python 3.12 and 3.13, with
  `careeros` and `careeros-mcp` entry points that do not depend on a source checkout.
- Added clean-environment wheel smoke coverage on Linux, macOS and Windows for package resources,
  migrations, CLI startup and the MCP initialization and tool-discovery handshake.

### Changed

- The GitHub release candidate now carries the Agent Access wheel and its exact hash-locked
  `requirements.lock` alongside the desktop artifacts, with both files covered by the release
  manifest, global checksums and GitHub provenance.
- Alembic configuration, templates and the complete historical migration chain now live inside the
  backend package so desktop, source and wheel installations use the same canonical resources.
- Agent Access installation resolves the reviewed dependency graph from `requirements.lock` before
  installing the wheel with dependency resolution disabled.

### Fixed

- CLI and MCP reads now open the vault through SQLite's read-only URI mode and enforce
  `PRAGMA query_only=ON` on every automation connection. Grant authorization and revocation remain
  isolated in a separate write-capable session.
- Installed Agent Access commands now find their model catalogue, taxonomy, AI fixtures and
  migration resources without relying on paths from a development checkout.

## [1.9.0] - 2026-07-30

### Added

- First-time users can now start the Career Vault from an existing CV. CareerOS creates the
  minimum local profile before the bounded source import, keeps extracted candidates unconfirmed
  and provides a direct keyboard-operable review step.
- Application dossiers now autosave one private, revisioned working draft per application in the
  local SQLite vault. Save failures and edit conflicts keep the current form intact, and users can
  retry, keep their local version or discard the saved draft explicitly.
- Added an authenticated Agent Access center for issuing, reviewing and revoking scoped CLI and
  MCP grants from the desktop. Bearers are shown once, never copied automatically and remain
  separate from the desktop session.

### Changed

- Publishing from the dossier workspace now consumes the exact saved draft atomically: the working
  copy is removed only in the transaction that records the immutable dossier version successfully.
  Existing API clients may still publish directly when no working draft exists.
- Portable backups now use archive format v6 so dossier drafts survive device migration, while
  formats v1 through v5 remain inspectable and restorable.
- The project Page now includes a branded 404 route, a repository-scoped crawler policy, one
  canonical sitemap, explicit no-Jekyll publishing and an RFC 9116 security contact that routes
  private reports through GitHub Security Advisories.
- Updated the reviewed direct Python dependencies to FastAPI 0.140.7, greenlet 3.5.4, httpx2
  2.9.1, Ruff 0.16.0, pre-commit 4.6.1 and types-reportlab 4.5.1.20260728, then regenerated the
  hash-locked application and development graphs with Python 3.12 and pip-tools 7.6.0.
- Updated the Page and responsive-browser checks to Playwright 1.62.0.

### Fixed

- Password reauthentication for Agent Access is serialized per account, limits repeated issuance
  attempts and still permits an authenticated user to revoke an owned grant during lockout.
- Agent Access now clears or compensating-revokes a one-time bearer when issuance finishes after
  sign-out, navigation or an unmount, and every management response is explicitly non-cacheable.
- Dossier saves re-check the application and resume binding after acquiring the SQLite writer
  transaction. Publication conditionally consumes only the exact draft revision that was reviewed.

## [1.8.0] - 2026-07-26

### Added

- Added a guided job-search workspace that starts from confirmed Career Vault facts, keeps CV
  upload as an explicit alternative and puts infrequent search controls behind a compact advanced
  section.
- Added durable, privacy-bounded search receipts so the home workspace can show real progress
  after runtime status has expired.
- Added first-seen, last-seen and content-revision metadata for job listings, including safe
  re-analysis when a provider changes an advert.
- Added direct Job Library links into the application pipeline, with one logical timeline per
  opportunity and application state visible in both desktop and mobile result cards.

### Changed

- The home workspace now guides a new user through Career Vault, local-model readiness, the first
  completed search and the first tracked application using only persisted product state.
- Lightweight profile screens use a paginated allowlist projection instead of transferring CV
  text, generated queries, snapshots or normalized payloads.
- Portable backups now use archive format v5 while remaining able to inspect and restore formats
  v1 through v4.
- Job and application ownership is resolved in bulk without N+1 queries, and legacy applied
  markers remain monotonic once an application has crossed an applied milestone.

### Fixed

- Prevented an older listing analysis or normalization result from overwriting a newer provider
  revision after asynchronous local-model work.
- Prevented local and international phone numbers from entering Career Vault-derived search
  snapshots while retaining years and ordinary numeric metrics.
- Enforced one application per user and logical opportunity at the database boundary, including
  concurrent creation attempts.
- Preserved or removed shared job-catalog rows correctly when a profile or complete vault is
  erased, including applications whose original Job row no longer exists.
- Prevented an out-of-order search completion from replacing the latest durable success receipt.
- Restored the database-managed `jobs.updated_at` default for installations created from the full
  migration history, so API and search-created rows no longer depend on an ORM-supplied timestamp.
- Replaced the deprecated `react-router-dom` v7 wrapper with React Router 8.3, removing the
  vulnerable RSC implementation tracked as `GHSA-qwww-vcr4-c8h2` even though CareerOS does not use
  the affected unstable RSC APIs.

## [1.7.0] - 2026-07-26

### Added

- Added a source-installed `careeros` CLI and a standard MCP stdio server for Codex, Claude Code
  and other local clients.
- Added seven bounded, typed read tools for product status, local-model readiness, Career Vault
  completeness, resume metadata, applications, readiness checks and the application agenda.
- Added password-authorized, account-bound grants with explicit scopes, expiry, one-time bearer
  display, digest-only storage, listing and revocation.

### Changed

- MCP now releases the desktop lease while idle, then reacquires it and revalidates the grant for
  every tool call. Revocation and expiry therefore take effect without restarting the server.
- Agent commands use a pinned, hash-locked source-install path with CI smoke coverage for both
  console entry points.
- Authorization now requires at least one explicitly selected read scope instead of granting a
  broad default.

### Fixed

- Configured the requested application-data directory before importing immutable settings or
  database state, including when inherited environment variables point elsewhere.
- Revoked active automation grants after a vault restore and removed them during complete vault
  erasure while preserving grants that belong to other local accounts.
- Redacted unexpected standalone MCP startup failures so bearer values, SQL diagnostics and local
  paths cannot escape through a traceback.

## [1.6.0] - 2026-07-24

### Added

- Added authenticated, rate-limited inspection for portable backup versions 1 through 4. The
  preflight validates archive structure, digests, typed records, relationships, application
  projections and file bindings without changing the current vault.
- Added a bilingual Backup Assurance Center that separates choosing and inspecting an archive from
  the later restore operation and keeps inspection available while the vault contains data.
- Added a narrow native backup writer that opens its own save dialog, verifies the service digest,
  re-reads the final file and restores a verified previous backup if promotion fails.

### Changed

- Backup inspection now reports structural validity, compatibility and current restore eligibility
  as separate facts through a bounded, content-free response.
- Desktop backup paths remain inside the Rust process. The renderer no longer receives a save path
  or permissions to write and rename sibling files.

### Fixed

- Prevented backup hashing and file I/O of up to 512 MiB from blocking the desktop main thread.
- Replayed current and historical application projections during preflight so inconsistent archive
  timelines fail before restore.
- Preserved the empty-vault requirement at restore time and documented that inspection eligibility
  is only a snapshot of the current destination state.

## [1.5.0] - 2026-07-23

### Added

- Added a private daily action agenda that groups owned applications into overdue, today,
  upcoming, unscheduled and needs-action queues with deterministic ordering and bounded results.
- Added explicit omission counts, browser-local day boundaries and automatic refresh at the next
  deadline or local midnight.

### Changed

- Agenda rows and category totals now come from one user-scoped SQL statement, so the compact list
  and its counts describe the same database snapshot without loading event, dossier or job payloads.
- The application workspace now cancels obsolete agenda requests and refreshes on focus, visibility
  and time boundaries while keeping agenda failures separate from the board.

### Fixed

- Hardened English, German, French and Italian requirement parsing for natural negations,
  alternatives, experience, language levels and qualifications, so missing mandatory evidence
  cannot be promoted to a strong match.
- Preserved the correct local day across both Zurich daylight-saving transitions.
- Returned a typed `422` response for invalid agenda windows instead of exposing transport-level
  validation details.
- Kept the agenda usable at 320 px with visible accessible labels, WCAG AA contrast and no
  overlapping controls.

## [1.4.0] - 2026-07-23

### Added

- Added a managed, local Qwen runtime with model download, lifecycle controls, readiness probes and
  actionable recovery diagnostics in the desktop interface.
- Added evidence-bound multilingual matching for English, German, French and Italian requirements,
  including alternatives, negations, experience, language level and qualification gaps.
- Added durable analysis provenance, content-free audit records and server-owned citations for
  every verified opportunity assessment.

### Changed

- Opportunity search, matching, recommendations and Career Coach now require a ready local model;
  Career Vault, documents, manual applications, exports, backups and deterministic readiness remain
  available while the model is unavailable.
- Model output is limited to a strict score contract. CareerOS derives decisions, caps, risks,
  citations and persisted assessment fields from server-owned evidence and policy.
- Job APIs, application snapshots and portable archives expose only verified local-model analysis;
  legacy, imported or client-authored analysis is quarantined rather than presented as trusted.

### Fixed

- Prevented malformed, truncated, extra-row or identity-mismatched model responses from reaching
  the job history, application pipeline or Career Coach.
- Prevented inferred requirements, unsupported coaching claims and tampered snapshot analysis from
  being promoted to user-visible facts.
- Moved private discovery queries off shared provider listings and onto each user's saved job, so
  one local account cannot read or overwrite another account's search terms.
- Preserved historical and restored Career Coach replies in explicit quarantine instead of
  deleting them, while keeping unauthenticated imported advice out of the active conversation.
- Kept inference endpoints restricted to loopback and exact, explicitly allowlisted container
  aliases while rejecting remote, private-network, link-local and malformed targets.

## [1.3.0] - 2026-07-22

### Added

- Added explicit-only, deterministic provider-query planning with a versioned provenance cache;
  CV prose and model-derived fields remain local matching inputs and cannot become search queries.
- Added private manual job capture with stable user-scoped identity, idempotent retries and no
  leakage into the shared provider catalogue.
- Added typed application next actions, canonical board projections, calendar exports and a
  versioned evidence dossier with deterministic ZIP manifests.
- Added bounded application summaries and detail payloads so the board remains responsive while
  complete timelines, tasks and dossiers stay available on demand.

### Changed

- Application archives now rebuild derived projections from snapshots and events. Modern v3
  archives are also checked against that replay before any restore is committed.
- The application workspace now distinguishes resume metadata loading, an empty library and a
  transport error, with accessible retry paths that preserve the dossier draft.
- Search status copy now reflects the explicit-query contract and the home workspace describes
  search and matching without obsolete model-planning language.
- CI now executes every opt-in performance acceptance gate, including 10k-record reads,
  application readiness and resume canvas budgets.

### Fixed

- Restoring historical v1, v2 and projection-free v3 application rows no longer leaves blank or
  stale board projections.
- Dossier evidence no longer appears empty when resume-version metadata or Career Vault evidence
  failed to load.
- Application deadlines remain timezone-aware and next-action ordering is deterministic across
  API responses, archives and calendar exports.

## [1.2.0] - 2026-07-22

### Added

- Added a deterministic Application Readiness Pack with nine inspectable checks for the role
  snapshot, application route, Career Vault profile, published resume files, document quality,
  profile freshness and confirmed resume evidence.
- Added canonical JSON and Markdown readiness exports with stable report fingerprints and an
  exact response-body SHA-256 digest.
- Added an in-place application-pack editor for the role title, company, description, application
  URL/email and owned published resume link, plus direct paths to Career Vault and Resume Studio.

### Changed

- The fictional offline demo now publishes verified PDF/DOCX resume artifacts, links them to the
  application and records the real readiness drawer at 100/100.
- Application preparation writes now require the expected revision and append a content-free
  timeline event naming only the fields that changed.

### Fixed

- Readiness now counts a published PDF or DOCX only after a contained read verifies its immutable
  digest and byte length; deleted, corrupt, unreadable, path-escaping and size-mismatched artifacts
  block the pack instead of passing from database metadata alone.
- Application Detail now behaves as a labelled modal on desktop and mobile, with dynamic keyboard
  focus containment, Escape close, inert and scroll-locked background, and reliable focus return.
- Concurrent detail loads use latest-request-wins cancellation, while application updates keep the
  drawer mounted and realign the next valid stage before another timeline write.
- Readiness Markdown escapes user-controlled role and company text so snapshots cannot inject
  links, formatting or HTML into exported reports.
- The Windows demo recorder now waits for child processes and retries bounded temporary cleanup,
  avoiding a post-publication directory race.

## [1.1.2] - 2026-07-20

### Fixed

- Replaced the third-party frontend license scanner with a deterministic lockfile audit after a newly disclosed transitive dependency advisory stopped the release gate.
- Kept production license evidence reproducible without publishing package-maintainer names, email addresses or local filesystem paths.

## [1.1.1] - 2026-07-20

### Changed

- Added the CareerOS mark to the desktop sidebar and the compact mobile header.
- Refined the public product page while keeping the real application tour as its only video.
- Credit shared work collectively without publishing individual contributor identities.

### Fixed

- Prevented the responsive app header from compressing or overflowing on narrow screens.

## [1.1.0] - 2026-07-20

### Added

- Public v1.0.2 release evidence with the six-platform verification runs, package sizes,
  digests and provenance-verification command.
- Complete English and Italian interface catalogues for sign-in, profile, search, schedules,
  application tracking, local AI, recovery and resume workflows.
- Deterministic release manifests, portable installer names, exact per-target and global
  SHA-256 inventories, three component SBOMs, and a reproducible evidence archive.
- Adversarial release tests for filename collisions, tampered bytes, incomplete evidence,
  stale drafts, duplicate releases, API ambiguity, and publication retries.

### Changed

- Devpost and README links now point to the verified native release while retaining the
  historical v1.0.0 evidence.
- The README now embeds the lightweight animated tour and routes full-video playback through
  GitHub Pages instead of GitHub's unsupported WebM file preview.
- Language changes now update validation, authentication, navigation and background-task
  feedback immediately, including messages that were already visible.
- Release publication now requires a verified annotated tag on the current default branch,
  verifies provenance before upload, and resumes safely after ambiguous GitHub API responses.
- Manual release runs are strictly read-only; only matching stable-version tag pushes can
  request OIDC credentials, create attestations, or publish a release.

### Fixed

- Downloadable checksum files now reference the exact canonical installer filenames.
- Release retries no longer overwrite, delete, or silently accept mismatched remote assets.

## [1.0.2] - 2026-07-19

### Fixed

- Replaced unsupported multi-extension artifact globs with explicit native package patterns.
- Added a pre-publication assembly job that verifies the complete 17-file release inventory
  during manual rehearsals as well as version-tag releases.

## [1.0.1] - 2026-07-19

### Added

- Public, responsive GitHub Pages portfolio with real product captures and the reproducible
  40-second tour.
- Code of Conduct, support guide, release-version consistency checks and coverage evidence.
- Transactional demo-media publishing with rollback tests, plus keyboard focus management for
  confirmation and mobile-navigation overlays.

### Changed

- Desktop packaging now uses a cross-platform hash-locked toolchain, native architecture and
  lifecycle checks, per-target SHA-256 inventories, build attestations and an all-or-nothing
  release publisher.
- CI enforces backend branch coverage, frontend coverage thresholds, complete script lint/type
  checks and atomic demo-recorder tests.
- Python is pinned to 3.12.10 across native release platforms, and zero-config SQLite startup
  creates its missing local vault directory.

### Fixed

- Prevented mobile menu controls from appearing in desktop captures and kept all Resume Studio
  actions visible at portfolio viewport sizes.
- Prevented partial demo recordings from replacing known-good public media.
- Corrected macOS PyInstaller resolution, hidden checksum uploads, release repository context,
  attestation glob parsing and checksum paths for downloadable installers.
- Kept the signed model catalog byte-identical on Windows checkouts, installed the missing
  Linux ARM desktop opener dependency, and made release-version fallbacks drift-proof.
- Removed a stale duration claim from the shared product-tour poster.

## [1.0.0] - 2026-07-18

### Added

- Career Vault, evidence-backed resume studio and immutable application pipeline.
- Managed local llama.cpp-compatible runtime with explicit consent and no cloud fallback.
- Transactional portable archives, secure vault erasure and Tauri sidecar lifecycle.
- Reproducible Playwright portfolio tour with isolated demo data and visual error gates.
- Clean workspace, Career Vault, Resume Studio and full pipeline captures.
- Portfolio-focused README, contribution guide and GitHub templates.
- Python, React, Rust, migration, supply-chain and packaging verification.

### Changed

- Optional local AI is presented as a neutral capability instead of an application failure.
- CI targets `main`, validates the Rust shell and uses a cross-platform Python dependency lock.
- Frontend tooling and containers use Node.js 24 LTS; the web build excludes desktop sidecars.

### Fixed

- Prevented React StrictMode from marking an unchanged resume canvas dirty and triggering an
  autosave/revision loop.
- Removed the rate-limit error and incomplete pipeline from public screenshots.

[Unreleased]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.11.1...HEAD
[1.11.1]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.11.0...v1.11.1
[1.11.0]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.10.0...v1.11.0
[1.10.0]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.9.0...v1.10.0
[1.9.0]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.1.2...v1.2.0
[1.1.2]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/ejupi-djenis30/careeros-local/releases/tag/v1.0.0
