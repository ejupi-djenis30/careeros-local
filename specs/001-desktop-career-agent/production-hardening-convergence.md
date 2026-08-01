# Production hardening convergence

## Closed findings

- Request bodies, provider and inference responses, document expansion, image normalization and
  managed-runtime acquisition are bounded before their expensive parser or persistence boundary.
- Source, photo and resume-artifact publication is create-if-absent. Durable journals and
  authoritative SQLite reconciliation cover process loss, concurrent winners and commit-result
  ambiguity without deleting bytes referenced by another local profile.
- Restore and complete-vault deletion no longer infer rollback from a raised `commit()`. A fresh
  independently locked snapshot proves the restore identity, ready lifecycle, complete bindings and
  durable bytes, or the deletion postcondition. Published outcomes continue forward; proven
  pre-commit failures compensate and remain retryable. Erasure session finalization accepts an
  ambiguous commit only after a fresh locked snapshot proves ready lifecycle, a null maintenance
  fingerprint and no remaining session owned by that account.
- Every persisted source/photo or resume-artifact restored from an archive has an integer, nonzero
  size within its table-specific ceiling before any byte is published. The member must also match
  that size, its SHA-256 digest and its canonical storage path.
- Export checks record, member, per-file and aggregate uncompressed limits before private reads and
  repeats the member invariant before ZIP assembly. Restore applies the same global member ceiling,
  closing the successful-but-unrestorable archive case.
- Private content and recovery-journal reads use bounded descriptor-stable regular-file reads.
  Symlink/reparse, hard-link, FIFO, identity-swap, size and digest failures close without exposing a
  private path. Windows retains pathname/descriptor identity and size checks but measures mutation
  stability between two `fstat` snapshots on the same descriptor, avoiding false NTFS timestamp
  drift without weakening swap detection.
- Installation-secret consumers share one canonical 43–256 byte ASCII reader. It validates the
  trusted path chain, regular-file identity, single-link status and stable descriptor; POSIX also
  proves current ownership and `0600` before the bytes become signing material.
- Stale atomic-write cleanup performs one globally bounded, non-following scan across assets and
  resumes, finishes discovery before unlinking and revalidates the root and parent identities at
  deletion time. Windows junctions cannot redirect the cleanup walk.
- SQLite target parsing, canonicalization and data-root containment have no filesystem side effect.
  The no-follow migration lock comes next; only inside it are the `0700` in-scope tree and `0600`
  database/sidecars created or repaired. Migration finishes before the lazy application engine
  connects, and runtime hooks avoid descriptor opens that could release POSIX process locks.
- Native readiness, backup publication, renderer IPC, release inventory, notices and architecture
  checks remain exact and fail closed. A raced backup destination is never replaced, and failed
  publication retains its recovery file.

## Executed evidence

These results are separate scopes and are not added together as one synthetic test total.

| Boundary | Exact result |
| --- | --- |
| Linux database and migration hardening, final focused round | 201 passed, 2 platform-specific skips; Ruff, format, mypy and diff checks passed |
| Windows database and private-storage focus | 60 passed, 15 POSIX-specific skips |
| Storage, restore and database audit baseline | 79 passed, 11 platform-specific skips |
| Repeated publication/storage concurrency | Five consecutive rounds; each round passed 75 tests with 1 platform-specific skip |
| Complete portability focus after member-symmetry correction | 48 passed |
| Lost-commit acknowledgement and installation-secret focus | 16 passed |
| Final recovery/storage suite after stable-read, restore-ceiling and erasure-finalizer fixes | 166 passed, 1 platform-specific skip in 72.25 seconds |
| Erasure-finalizer lost-acknowledgement regression focus | 5 passed |
| Alembic clean-root lifecycle | `upgrade head`, `downgrade -1`, then `upgrade head` passed; final revision `a9b0c1d2e3f4`; `PRAGMA quick_check=ok` |
| Frontend unit/component suite | 79 files and 476 tests passed under Node 24.18.x |
| Frontend distribution contracts | Runtime preflight 4 passed; license checks 6 passed; 123 workspace and 9 lifecycle icons drift-checked; lint and production build passed |
| Production renderer budgets | Entry JavaScript 326,863 bytes raw / 103,689 gzip; lifecycle CSS 21,837 / 5,841; initial load 424,563 / 133,965; authenticated CSS 427,732 / 70,792 |
| Real Chromium | Portfolio responsiveness 15 passed; agenda 4 passed; workspace shell 4 passed; login contrast measured 7.60:1 and 7.96:1; Agent Access WCAG/responsive gate passed |
| Native Rust | `cargo fmt --check`, all-target/all-feature clippy with warnings denied, and all-feature tests passed; 27 library tests passed, with 0 main/doc failures |
| Static supply-chain boundary | Three GitHub Actions workflows passed `actionlint`; Trivy reported 0 HIGH/CRITICAL findings for CareerOS npm, Cargo and Python dependency scopes and 0 HIGH/CRITICAL secret/misconfiguration findings |

The clean Alembic QA root was removed after an exact containment check. Focused browser and backend
fixtures used disposable local state; no commit, push, release publication or deployment occurred.

## Final release evidence

**Full backend coverage:** `.venv\Scripts\python.exe -m pytest tests/backend -q --cov=backend
--cov-report=term-missing --cov-fail-under=80` completed with
`2177 passed, 15 skipped in 946.80s (0:15:46)` and 84.90% total coverage, above the required 80%
threshold.

**Opt-in performance budgets:** with `RUN_PERFORMANCE_TESTS=1`, all four backend benchmarks passed
in 9.05s. On 10,000 application records, profile reads reached 6.62ms p95, paged application reads
57.95ms p95 and agenda reads 139.77ms p95 against the 200ms budget. Verified application readiness
reached 26.43ms p95 against 100ms while staying within five queries; deterministic generation from
1,000 career facts and detailed resume reads also remained within their 500ms and 200ms budgets.

**Post-freeze Windows packaging:** after the final installer hardening pass, the canonical command
`.venv\Scripts\python.exe -m pytest tests\backend\release
tests\backend\unit\test_release_versions.py -q` completed with
`155 passed in 83.89s (0:01:23)`. It covers MSI/NSIS ownership isolation across the explicit
32/64-bit registry views, fail-closed full and `/UPDATE` uninstalls while MSI owns the payload,
rollback after a completed install whose later smoke fails and after a non-zero partial install
that produced exactly one uninstaller, fail-fast readiness evidence and the declared x64/ARM64 PE machine type. The two
consecutive frontend production builds under Node 24.18.0 each produced the same 29 files and
2,649,594 bytes with aggregate SHA-256
`1af01afc6e3c275e1c752398a63aa297329a0086374cedad93287affa15cc296`; all bundle budgets remained
green. The rebuilt native artifacts were recorded exactly as follows:

| Artifact | Inventory | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Frozen sidecar executable | 1 file | 18,657,969 | `7f414d7fe815bf457e3ca110789e066bc7ebb15c08a14787d965ddc3f5e7cc1a` |
| Schema-2 `onedir` runtime | 1,003 files | 86,332,208 | `ce10760074d27d186eb51a34bf85a934fe1c50bfa631bb73026dab1d9c7fa89f` |
| MSI installer | 1 file | 48,810,167 | `316415b36f588b6c9e772f9171abd39a1173dbd0a94d8cf027ed9f3cfe81e933` |
| NSIS installer | 1 file | 38,522,425 | `bdfeba813e742df76c686b18733449d5695fd5d4ffabe2c84c3a59a3f218bb19` |

The frozen backend generated PDF, DOCX and portable-backup artifacts and exited cleanly. The
Windows harness administratively extracted the MSI and performed a real NSIS install and uninstall,
covering first launch, authenticated readiness, offline reopen, database and vault preservation,
PDF/DOCX/backup output, exit code 0 and zero orphaned sidecars. Before the successful uninstall it
created the exact four MSI-owned values in Registry64, proved that both normal and `/UPDATE` NSIS
uninstalls returned non-zero while leaving the application, backend, uninstaller and registration
intact, removed only those simulated values, and then required the complete NSIS installation root
to disappear. A separate real MSI installation
opened the native UI, passed the installed-backend smoke and uninstalled by ProductCode. The final
audit found no installed file, ARP entry, CareerOS process, shortcut, HKCU application key,
now-empty parent key or `.artifacts/i` harness directory; the user-owned vault remained intact.

This evidence closes T231 without lowering a test threshold or security check.

## Residual operating boundaries

- The supported vault is local NTFS or a local POSIX filesystem. SMB, NFS, userspace and
  cloud-synchronised filesystems remain outside the locking and durability contract.
- A malicious process already running as the same local UID/account can still race path components.
  Closing that class completely requires platform-specific directory handles or `openat2`-style
  traversal across the full storage layer.
- POSIX mode checks do not audit extended ACLs. On Windows, CareerOS relies on the per-user
  application-data ACL because Python does not provide an equivalent portable owner/mode and
  directory-fsync proof.
- Portable archives are integrity checked but are not encrypted or independently signed. Exported
  backups still require encrypted custody and authenticated transfer by the operator.
- The locally rebuilt installers were not published or deployed and remain unsigned. Windows
  signing, Apple signing/notarization and Linux distribution signing require owner credentials and
  the platform release matrix.
- WebKit cannot launch on this Windows ARM64 host because host process creation returns `UNKNOWN`;
  the supported CI matrix retains that browser gate. Windows Application Control blocks Semgrep
  before launch on this host, so this convergence does not substitute or claim a clean Semgrep run.
