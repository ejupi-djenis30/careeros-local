# Changelog

All notable changes to CareerOS Local are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [Unreleased]

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

[Unreleased]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.5.0...HEAD
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
