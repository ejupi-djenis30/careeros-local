# Changelog

All notable changes to CareerOS Local are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [Unreleased]

### Added

- Reproducible Playwright portfolio tour with isolated demo data and visual error gates.
- Clean workspace, Career Vault, Resume Studio and full pipeline captures.
- Portfolio-focused README, contribution guide and GitHub templates.

### Changed

- Optional local AI is presented as a neutral capability instead of an application failure.
- CI targets `main`, validates the Rust shell and uses a cross-platform Python dependency lock.
- Frontend tooling and containers use Node.js 24 LTS; the web build excludes desktop sidecars.

### Fixed

- Prevented React StrictMode from marking an unchanged resume canvas dirty and triggering an
  autosave/revision loop.
- Removed the rate-limit error and incomplete pipeline from public screenshots.

## [1.0.0] - 2026-07-18

### Added

- Career Vault, evidence-backed resume studio and immutable application pipeline.
- Managed local llama.cpp-compatible runtime with explicit consent and no cloud fallback.
- Transactional portable archives, secure vault erasure and Tauri sidecar lifecycle.
- Python, React, Rust, migration, supply-chain and packaging verification.

[Unreleased]: https://github.com/ejupi-djenis30/careeros-local/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/ejupi-djenis30/careeros-local/releases/tag/v1.0.0
