# CareerOS Local v1.1.0 release preparation

Date prepared: 2026-07-20

Status: candidate contract implemented; no tag or GitHub Release was created by this change.

Cross-artifact result: [v1.1 release-contract convergence](release-convergence-v1.1.0.md).

## Source contract

- Version: `1.1.0` in all seven authoritative sources.
- Planned tag: `v1.1.0`, stable SemVer only.
- Publication source: a GitHub-verified annotated tag resolving to the exact workflow commit and
  contained in the current default branch.
- Publication trigger: matching tag push only. Pull requests, schedules, and manual dispatches
  have read-only repository permissions and cannot request OIDC or attest/publish.

## Candidate contract

The release pipeline stages each native target independently and rejects symbolic links,
unrecognized targets, duplicate package types, unsafe filenames, and case-insensitive name
collisions. Assembly accepts exactly six target manifests and creates exactly 22 public assets:
10 packages, six exact target checksums, three CycloneDX SBOMs, the deterministic evidence archive,
the global manifest, and `SHA256SUMS`.

Every recorded release asset must be non-empty. Each macOS job verifies the exact DMG with
`hdiutil`, mounts it read-only, exercises the backend and application from the mounted `.app`, and
detaches the image before the DMG can enter the canonical candidate.

The manifest records the exact target, package type, name, byte size, SHA-256 digest, source commit,
release date, SBOMs, evidence members, evidence archive, and MIT `LICENSE` digest. Package names do
not contain spaces, so every downloadable checksum line can be passed directly to
`sha256sum --check`.

## Publication contract

The publisher scans every release page and every asset page. It rejects duplicate tag releases,
stale CareerOS drafts, foreign draft state, version regressions, unexpected assets, and any
name/size/digest mismatch. It never uses clobber, delete, or replace operations.

Create, upload, and publish responses that are lost after the server accepts them are reconciled
against the durable contract. A later retry resumes missing uploads, while a completed immutable
latest release returns without a write. Final checks cover release ID, tag, exact source commit,
name, notes, draft/prerelease/immutable state, latest status, and all 22 asset digests.

## Local verification recorded for this change

- Release/version/policy tests: 42 passed after canonical-date, exact three-SBOM verification,
  API-token exfiltration, non-empty package, and mounted-DMG lifecycle cases were added.
- Full backend suite: 986 passed, 3 skipped, 80.17% branch-aware coverage.
- 10,000-record performance acceptance: 15.459 ms application-page p95 and 5.195 ms
  profile-read p95 against a 200 ms budget.
- Python static gates: Ruff passed; mypy passed for `backend` and `scripts`.
- Frontend: 51 files and 274 tests passed with coverage; ESLint and the Vite production build
  passed. The first run, executed concurrently with a cold Rust build, timed out in one
  accessibility test; the complete isolated rerun passed.
- Rust: `cargo fmt --check`, locked Clippy with `-D warnings`, and locked tests passed (6 tests).
- Migrations: `upgrade head`, `downgrade -1`, and `upgrade head` passed on a fresh SQLite database.
- Dependency gates: all three hash-locked Python audits and npm high-severity audit reported no
  known vulnerabilities; Cargo audit passed with the repository's narrow, unexpired
  `RUSTSEC-2024-0429` exception and reported 16 allowed unmaintained warnings; Cargo license
  policy passed.
- Workflow syntax/policy: actionlint passed for every workflow.
- Local tool versions: Python 3.12.13, Node.js 24.14.0, Rust/Cargo 1.96.0, actionlint 1.7.12,
  and GitHub CLI 2.94.0. The workflow itself pins Python 3.12.10 and Node.js 24.18.0; those exact
  versions remain for pull-request CI to verify.

These are implementation checks, not release evidence. Native matrix results, artifact sizes,
digests, GitHub attestation records, and immutable release identity must be added only after an
authorized tag workflow completes successfully.
