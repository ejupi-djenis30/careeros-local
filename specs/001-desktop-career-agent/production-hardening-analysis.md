# Production hardening analysis

## Scope and method

This slice reviews the complete CareerOS Local production boundary after Phase 30: ASGI input,
provider and inference transports, managed-runtime acquisition, SQLite startup and migration,
content-addressed private storage, portable archives, the native sidecar, Tauri IPC, installer
assembly and the unauthenticated renderer path. It adds no cloud service, telemetry, shared vault,
remote agent transport or automatic publication.

The review combined source-level threat modelling, fault injection, repeated SQLite writers, raw
HTTP and compressed-response adversaries, real Chromium, native Rust tests, a frozen PyInstaller
sidecar, and installed MSI/NSIS lifecycle checks. Every file and database test used synthetic data
under a disposable root. The existing user Docker stack was observed only through read-only health
and metadata checks.

## Converged boundaries

### Transport and parser budgets

- ASGI rejects duplicate or ambiguous framing and enforces exact route-specific byte ceilings while
  receiving the body, before multipart, JSON or document parsing can allocate beyond the policy.
- Job providers and local inference accept only identity-encoded, bounded responses with exact
  content contracts. Redirects, compressed expansion, slow streams, mismatched models and malformed
  usage metadata fail closed.
- PDF, DOCX, text and photo preparation has member, page, character, pixel, compressed and
  uncompressed ceilings. CPU-heavy parsing and normalization run outside the SQLite writer lock.
- Managed-runtime downloads use a fixed allowlist, redirect and byte limits, free-space preflight,
  checksummed inventory, continuous file attestation, bounded cancellation and owned process trees.

### SQLite and private filesystem state

- One packaged Alembic chain is used by source, container, wheel and frozen applications. Target
  parsing, canonical resolution and data-root containment are side-effect free; only then does
  startup acquire the bounded no-follow OS migration lock. Inside that lock it creates and hardens
  the in-scope directory chain, privately reserves a new database, writes a checksummed recovery
  marker, includes WAL frames in the migration backup and restores atomically after a failed or
  interrupted upgrade.
- Startup migration completes before the lazy application engine can create its first pooled
  handle. Database, lock, recovery, secret and backup paths reject URI ambiguity, symlink/reparse
  aliases, unexpected hard links and special files at their respective trust boundaries. New local
  database directories are private (`0700`) and SQLite main/WAL/SHM/journal files are kept at
  `0600` on POSIX; Windows relies on the per-user application-data ACL. Runtime connection hooks
  use lstat-only validation so closing an auxiliary descriptor cannot release a process-scoped
  POSIX SQLite lock.
- Content-addressed source, photo and resume publication uses create-if-absent ownership. A losing
  writer cannot replace or remove a winner's bytes, and deletion preserves paths referenced by a
  different local profile. A strict, size-bounded recovery journal is durable before source or
  photo bytes are published, so process loss and commit-result ambiguity converge from the
  authoritative SQLite state on startup or before the next writer.
- Portable restore and complete-vault deletion treat an exception from an attempted commit as an
  ambiguous outcome. A fresh independently locked SQLite snapshot proves the unique restore
  identity, lifecycle, database bindings and durable files, or the complete deletion postcondition,
  before any compensation occurs. A published restore therefore keeps its rows and files; a
  published deletion finishes privacy cleanup instead of restoring staged bytes. A proven
  pre-commit failure retains the established rollback and retry behavior. The separate erasure
  session-finalization commit uses the same rule and accepts success only when a fresh snapshot is
  ready, has no maintenance fingerprint and contains no session owned by that account.
- Verified private-file reads require canonical in-root paths, recorded sizes, explicit per-file
  ceilings, stable regular-file metadata and SHA-256 equality. POSIX opens are non-blocking so a FIFO
  cannot pin a worker before the regular-file check. Resume-publication and restore journals use the
  same bounded descriptor-stable primitive and reject symlink/reparse and hard-link aliases. On
  Windows, path-versus-descriptor timestamps are not compared because NTFS API representations can
  drift; path/descriptor identity and size are still proven, while mutation timestamps are compared
  across two `fstat` snapshots on the same open descriptor and final path identity is revalidated.
- Crash-left atomic-write cleanup uses an explicit globally bounded directory walk, never follows
  a symbolic link or Windows junction, completes both private namespaces before deleting anything,
  and revalidates the directory chain immediately before each unlink.
- Portable export preflights record count, every file size, the ZIP member count and the aggregate
  uncompressed budget before reading a private member. Restore independently requires a non-Boolean
  integer byte size within the source/photo or resume-artifact per-file ceiling before publication,
  then proves the bound member's exact size and digest. Payload and manifest bytes remain inside the
  aggregate ceiling, and corruption is mapped to a redacted archive error rather than leaking a
  path or becoming an accidental 500. The export and restore member limits are symmetric, so an
  accepted export cannot exceed the restore member envelope.

### Native desktop and release boundary

- The installation secret is written completely to a private temporary inode and published without
  replacement. Startup can settle only the one canonical two-link kill window; unknown aliases are
  preserved and rejected. Container, CLI and MCP consumers independently require canonical ASCII,
  a 43–256 byte bound, one stable regular-file descriptor, one link, and a non-linked private path
  before those bytes can become signing material.
- POSIX directory and secret ownership/modes are changed and verified through open descriptors with
  `fstat`/`samestat`/`fchmod`. Windows continues to rely on the per-user application-data ACL.
- Native readiness accepts at most 8 KiB within one total second and requires an exact HTTP 200,
  JSON media type, content length and `{"status":"ready"}` body.
- Rust backup publication is create-if-absent and cannot overwrite a destination created after the
  save dialog check. A failed publication retains the recovery file. Renderer IPC accepts at most
  the backend's 128 MiB raw archive ceiling; 129 MiB is reserved only for HTTP multipart overhead.
- Release candidates bind the sidecar manifest, target architecture, GUI subsystem, licenses,
  notices, SBOM inputs and native bundle inventory before an installer can be accepted.

## Findings found during convergence

| Finding | Failure mode | Resolution |
| --- | --- | --- |
| Body limit applied after parsing | multipart/compressed input could allocate first | ASGI receive wrapper and route ceilings |
| Unbounded provider/inference read | remote or loopback stream could exhaust memory | identity-only bounded streams and strict schemas |
| Replace-based content publication | losing transaction could delete winner bytes | hard-link create-if-absent ownership and race tests |
| Publication had no durable pre-write ownership record | process loss between bytes and SQLite commit could orphan private files | strict journal before publication plus DB-authoritative reconciliation |
| Restore/deletion compensated every commit exception | a lost acknowledgement could remove committed restore files or resurrect committed deletion bytes | fresh locked authoritative postcondition checks distinguish published commits from rollback |
| Erasure session finalization treated every commit exception as failure | a lost acknowledgement could report failure after sessions and retry authority were already removed | fresh locked ready/null-fingerprint/zero-session postcondition accepts only the published finalization |
| Verified file read used `read_bytes()` | tampered large file could allocate before SHA check | exact size/maximum and stable descriptor read |
| Stable read compared path and descriptor timestamps on Windows | equivalent NTFS metadata surfaced through different APIs could cause false tamper failures under load | retain identity/size/link checks and compare mutation timestamps only across two descriptor snapshots |
| Recovery metadata used ordinary pathname reads | oversized or exchanged journals could bypass the intended recovery envelope | bounded descriptor-stable reads with link/type/identity checks |
| CLI/config read the installation secret with `read_text()` | linked or oversized files could be followed and used as signing material before the desktop lease | shared bounded canonical reader with path, identity, ownership and mode revalidation |
| POSIX FIFO opened in blocking mode | worker could wait forever before `fstat` | `O_NONBLOCK` plus FIFO regression |
| Export accumulated files without an aggregate budget | many valid files could exceed the archive memory model | metadata preflight and one uncompressed ceiling |
| Export did not preflight its own ZIP member count | a valid export could exceed the restore member limit and become unrestorable | symmetric member preflight before private reads plus a final invariant |
| Restore trusted archive-declared private-file sizes | empty or per-table oversized files could become durable state that a later export rejects | integer-only `1..limit` validation for source/photo and resume-artifact records before publication |
| SQLite state was created before lock validation | a rejected migration lock could still leave directories or an empty database | side-effect-free target validation, then no-follow migration lock, then private reservation |
| Migration followed an already-open pooled handle | new vault could gain WAL/empty-backup side effects | dispose, migrate, then readiness |
| Database validation briefly opened a second descriptor | POSIX close could release the process migration lock because `fcntl` locks are process-scoped | lstat-only connection hook after locked startup validation |
| Stale-write cleanup used recursive path enumeration | a Windows junction could carry cleanup outside the private namespace | non-following bounded `scandir`, two-namespace preflight and unlink-time chain validation |
| Secret written directly to final path | kill could leave a truncated accepted file | fsync temporary inode and no-clobber publication |
| Readiness used substring matching and `read_to_end` | spoofed or slow response could be accepted or block | bounded exact HTTP/JSON parser |
| Native backup used replace semantics | raced destination could be overwritten | no-clobber publication with recovery preservation |

## Threat model and residual limits

- The supported vault is on local NTFS or a local POSIX filesystem. SMB, NFS, userspace and
  cloud-synchronised folders are outside the locking and durability contract.
- Filesystem checks protect the dedicated CareerOS identity from other host identities. A malicious
  process already running as that same identity can still race pathname components; complete closure
  would require platform-specific directory handles or `openat2`-style traversal throughout the
  storage layer.
- POSIX modes do not audit extended ACLs. Windows does not expose an equivalent portable directory
  fsync or owner/mode proof through Python; the per-user ACL and recovery journals remain the stated
  boundary.
- Local archives are integrity checked, not encrypted or independently signed. Operators remain
  responsible for encrypted custody and authenticated transfer of exported backups.
- Native packages built locally are unsigned. Windows signing, Apple signing/notarization and Linux
  distribution signing require owner credentials and their platform release jobs.
- WebKit cannot launch on this Windows ARM64 host because process creation is blocked by the host
  environment; supported CI runners retain the WebKit gate. Semgrep is likewise blocked before
  launch by Windows Application Control, so no substituted clean result is claimed.
