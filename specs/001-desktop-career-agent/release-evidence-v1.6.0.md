# CareerOS Local v1.6.0 release preparation

Date prepared: 2026-07-24

Status: local release-candidate implementation and independent review completed. Protected-branch
CI, the native matrix rehearsal and signed-tag publication remain the remote release gates.

Cross-artifact results:

- [Backup assurance analysis](backup-assurance-analysis.md)
- [Backup assurance convergence](backup-assurance-convergence.md)

## Candidate scope

v1.6.0 separates backup inspection from restore. An authenticated, rate-limited endpoint accepts
portable archives from versions 1 through 4, runs the complete preflight in memory and returns a
bounded content-free summary. Inspection remains available while the Career Vault contains data;
restore is a later operation that validates the archive again and still requires an empty vault.

Preflight covers manifest and member digests, typed decoding, record relationships, current and
historical application projections, file bindings and path containment. A structurally valid
archive can therefore be reported as valid but not currently restorable without weakening either
claim.

The desktop save boundary also moved into Rust. The native command opens its own save dialog, so
the selected path never enters the renderer. It verifies the service digest, writes through a
random sibling part file, flushes and re-reads the bytes, promotes the file and verifies the final
destination. If replacement fails after the previous file moved aside, the command verifies and
restores that prior file.

All seven authoritative version sources report `1.6.0`; the planned stable tag is `v1.6.0`.

## Local verification recorded for this candidate

- Version contract: `python scripts/check_release_versions.py --expected-tag v1.6.0` reports
  `RELEASE_VERSION=1.6.0 SOURCES=7`.
- Backend: 1,369 tests passed with 4 expected performance skips. The focused independent review
  reran 42 portability and storage tests.
- Python static checks: Ruff passed for backend, tests, migrations and scripts; mypy passed for
  backend and scripts.
- Frontend: 64 files and 334 tests passed. The independent recovery, platform and service slice
  reran 12 tests; ESLint and the production Vite build passed.
- Rust: formatting and locked Clippy with warnings denied passed. `cargo test --all-targets`
  passed all 17 library tests, including native writer replacement, corruption and rollback paths.
- Packaging inputs: the Tauri capability schema was regenerated and the frontend license
  inventory passed all three checks.
- Hygiene: `git diff --check` passed.

The packaged-binary smoke test and complete native matrix remain mandatory in the existing allowed
CI and release runners.

## Claims and boundaries

- Inspection is non-mutating, but its `restorable` value only describes destination state at that
  moment. Restore validates everything again.
- Portable ZIPs are not encrypted or authenticated. SHA-256 detects changed bytes; it does not
  identify the archive's author.
- The native desktop path is verified before and after writing. In browser mode, CareerOS can only
  verify bytes before handing them to the browser's download mechanism.
- Parent-directory synchronization is explicit on Unix. Rename and power-loss durability retain
  the guarantees of the destination filesystem and operating system.

## Publication sequence

1. Merge the reviewed candidate through protected `main` with every required check green.
2. Review the read-only native matrix rehearsal on the exact merge commit.
3. Create the verified annotated `v1.6.0` tag with the authorized signing identity.
4. Let the tag workflow build, attest, verify and publish the immutable release; do not alter it
   manually.
