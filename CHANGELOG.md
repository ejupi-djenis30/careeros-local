# Changelog

All notable changes to CareerOS Local are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [Unreleased]

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

[Unreleased]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/ejupi-djenis30/careeros-local/releases/tag/v1.0.0
