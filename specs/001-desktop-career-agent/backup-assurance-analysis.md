# Backup assurance center — cross-artifact analysis

Date: 2026-07-24

## Decision under review

CareerOS Local now verifies a portable backup before a user has to empty the Career Vault.
Verification and restore are different operations. Verification accepts supported archives with a
populated vault, validates the complete archive in memory, reports whether the current destination
can accept it, and writes nothing. Restore still requires an empty vault.

The desktop save boundary also changed. JavaScript verifies the export response digest, then sends
bounded raw bytes, the digest, and a validated suggested filename to a narrow Rust command. That
command runs off the main thread, opens the native save dialog itself, and never returns the selected
destination to JavaScript. It owns temporary files, read-back verification, rename, rollback, and
cleanup.

## Contract analysis

| Boundary | Implementation evidence | Result |
| --- | --- | --- |
| Archive validity | Inspection reuses member limits, manifest hashes, typed decoding, relationship checks, application replay, and file-binding containment | Converged |
| Destination state | ID and empty-vault conflicts affect `restorable`; they do not make a structurally valid backup invalid | Converged |
| Zero mutation | Inspection prepares contained writes in memory under the vault lock but never opens a destination file or adds a database row | Converged |
| Content-free response | The fixed schema returns digest, version, creation time, counts, byte totals, compatibility, restore eligibility, and stable codes only | Converged |
| Untrusted projections | Current and historical application timelines are replayed before restore or inspection; inconsistent read-model projections fail preflight | Converged |
| API boundary | `POST /portability/inspect` is authenticated, rate-limited, multipart, and capped at the archive byte limit | Converged |
| AI trust | Unsigned imported analysis remains quarantined and requires the installed local model's current validation | Converged |
| Recovery interface | English and Italian UI separates choose-and-verify from restore, keeps verification available with data present, and exposes an accessible summary | Converged |
| Native destination write | Rust checks the payload digest, reserves a random part sibling with `create_new`, uses a distinct random rollback sibling, flushes, re-reads, promotes, re-verifies, and restores a verified prior file on failure | Converged |
| Least privilege | Rust owns the save dialog and destination; the webview retains open-dialog and scoped read-file permission but has no save-dialog, write, rename, remove, or directory capability | Converged |
| Browser honesty | Browser mode checks bytes before handoff and explicitly says that the final download destination cannot be verified | Converged |
| Persistence | No table, column, index, or historical row changes; no migration is required | Converged |

## Adversarial review

Backend coverage inspects archive versions 1 through 4 with a populated vault and checks database
counts, revisions, and managed files before and after the call. It rejects manifest/member checksum
changes, traversal members, inconsistent application projections, unauthenticated requests, and
oversized uploads through stable content-free errors. The response is checked against private
profile text, source bytes, source names, storage paths, and identifiers.

Native coverage rejects a response-header checksum mismatch before writing. Rust tests cover a new
destination, replacement of an existing backup, corruption after promotion, verified rollback,
directory destinations, and Windows reparse-point destinations when symlink creation is available.
Every successful or recovered test leaves no CareerOS sidecar. The writer runs outside the main
thread, and a process-local mutex prevents two renderer save requests from interleaving.

## Verification result

- Backend: 1,369 passed, 4 expected skips. The focused portability file contributed 26 passing
  tests.
- Frontend: 64 files and 334 tests passed. The focused recovery, platform, and service slice
  contributed 12 passing tests.
- Rust: all 17 library tests passed after the native path/thread hardening, including the
  dialog-title validator. `cargo test --all-targets`, formatting and Clippy with warnings denied
  passed.
- Static analysis: Ruff passed over backend, backend tests, migrations, and scripts; mypy passed
  over backend and scripts; ESLint passed over the full frontend.
- Packaging inputs: the Vite production build passed and generated the current Tauri capability
  schema. The frontend license inventory passed all 3 checks.
- Hygiene: `git diff --check` passed.

The packaged-binary smoke test and cross-platform native matrix still belong in the existing
allowed CI and release environment; the local Rust source and test targets are green.

## Residual platform boundaries

Portable ZIPs remain unencrypted and unauthenticated. Checksums detect changed bytes, not authorship.
File data is flushed on every supported desktop platform. Parent-directory synchronization uses the
standard directory handle on Unix; Windows and unusual destination filesystems retain their native
rename and durability semantics. Browser mode cannot re-open a download after the browser owns it.
The interface and documentation state each limitation directly.
