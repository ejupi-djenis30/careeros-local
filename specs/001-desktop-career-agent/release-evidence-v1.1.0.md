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
collisions. Assembly accepts exactly six target manifests and creates exactly 23 public assets:
10 packages, six exact target checksums, three CycloneDX SBOMs, the deterministic evidence archive,
the canonical LF `LICENSE`, the global manifest, and `SHA256SUMS`.

Every recorded release asset must be non-empty. Tauri maps the repository `LICENSE` to the native
resource root. Platform smoke gates then inspect real extracted, mounted, or installed payloads:
MSI, NSIS, AppImage, DEB, and both DMG architectures must expose the byte-identical approved
project notice at the canonical Tauri resource root, with no lowercase duplicate or symlink alias.
Each macOS job also verifies the exact DMG with `hdiutil`, mounts it read-only, exercises the
backend and application from the mounted `.app`, and detaches it before the DMG can enter the
canonical candidate.

The manifest records the exact target, package type, name, byte size, SHA-256 digest, source commit,
release date, SBOMs, evidence members, evidence archive, and the exact downloadable MIT `LICENSE`
asset. Arbitrary or changed text cannot be labelled SPDX MIT. Package names do not contain spaces,
so every downloadable checksum line can be passed directly to `sha256sum --check`.

## Publication contract

The publisher scans every release page and every asset page. It rejects duplicate tag releases,
stale CareerOS drafts, foreign draft state, version regressions, unexpected assets, and any
name/size/digest mismatch. It never uses clobber, delete, or replace operations.

All tag-triggered workflows share one cross-tag concurrency group, with cancellation disabled for
the running tag. GitHub may supersede an older pending run when another tag arrives, so operators
must confirm every intended tag workflow completed. After uploads complete, the publisher
discovers every release page again and rechecks version ordering immediately before promotion, so
a delayed older tag cannot replace a newer immutable latest release.

Create, upload, and publish responses that are lost after the server accepts them are reconciled
against the durable contract. A later retry resumes missing uploads, while a completed immutable
latest release returns without a write. Final checks cover release ID, tag, exact source commit,
name, notes, draft/prerelease/immutable state, latest status, and all 23 asset digests.

## Local verification recorded for this change

- Release/version/policy tests: 64 passed (59 adversarial release/policy tests plus five version
  tests) after canonical-date, canonical-license, lowercase-duplicate and symlink-alias rejection,
  exact target set, off-branch tag, later-page duplicate, cross-tag race, exact three-SBOM
  verification, API-token exfiltration, non-empty package, and mounted-DMG lifecycle cases were
  added.
- Full backend suite: 1008 passed, 3 skipped. The previously recorded branch-aware coverage remains
  80.17%; this patch does not change production modules under `backend/`.
- 10,000-record performance acceptance: 85.299 ms application-page p95 and 18.496 ms
  profile-read p95 against a 200 ms budget.
- Python static gates: Ruff passed; mypy passed for `backend` and `scripts`.
- Frontend: 51 files and 274 tests passed; ESLint and the Vite production build passed after a
  clean, lockfile-driven `npm ci` install for the local Windows ARM64 runtime.
- Rust: `cargo fmt --check`, locked Clippy with `-D warnings`, and locked tests passed (6 tests).
- Windows ARM64 package proof: a locked production Tauri build produced a 41,642,839-byte MSI and
  a 33,033,060-byte NSIS installer. The real package gate passed MSI administrative extraction,
  NSIS install/uninstall, DOCX/PDF export, initial and offline reopen, sidecar shutdown, vault-data
  preservation, and exact verification of the canonical 1,069-byte `LICENSE` at both resource
  roots (`7e1d73415a3de7fa896ac8871ae0aea8fc736e9f0d274bf658c18399236976c6`).
- Migrations: `upgrade head`, `downgrade -1`, and `upgrade head` passed on a fresh SQLite database.
- Dependency gates: all three hash-locked Python audits and npm high-severity audit reported no
  known vulnerabilities; Cargo audit passed with the repository's narrow, unexpired
  `RUSTSEC-2024-0429` exception and reported 16 allowed unmaintained warnings; Cargo license
  policy passed.
- Workflow syntax/policy: actionlint passed for every workflow.
- Local tool versions: Python 3.12.13, Node.js 24.16.0, Rust/Cargo 1.96.0, actionlint 1.7.12,
  and GitHub CLI 2.94.0. The workflow itself pins Python 3.12.10 and Node.js 24.18.0; those exact
  versions remain for pull-request CI to verify.

These are implementation checks, not release evidence. The Windows package proof above does not
replace the read-only six-platform rehearsal. Native matrix results, artifact sizes, digests,
GitHub attestation records, and immutable release identity must be added only after an authorized
tag workflow completes successfully.
