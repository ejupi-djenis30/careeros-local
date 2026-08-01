# Crash-recoverable vault lifecycle analysis

## Purpose

Reset, restore and complete erasure previously depended too heavily on one process lifetime. A
crash could leave published files or partially completed cleanup without a durable account-level
reason to deny ordinary access. This slice makes destructive work restart-recoverable, gives the
user one password-protected path to convergence and keeps liveness responsive while the vault is
quiesced. It does not add remote storage, another credential store or background telemetry.

## Durable state and authority

`User.vault_lifecycle_state` has exactly four values. `ready` is the sole normal-workspace state;
`reset_pending`, `restore_pending` and `erasure_pending` survive process loss. Only restore stores a
fingerprint, and it is the lowercase SHA-256 of the verified ZIP. Database checks bind those fields.
The migration backfills `ready` without changing vault records and refuses downgrade while an
account is pending.

Session issuance and lifecycle transitions serialize on the owner row. SQLite ends a stale read
snapshot and takes `BEGIN IMMEDIATE`; other databases use row locking. Reset and erasure perform a
second family sweep immediately before completion, so a login that raced the first snapshot cannot
retain authority. Normal access, refresh, automation authentication and grant issuance require
`ready` plus a signed `purpose=session` family.

Correct-password login during recovery returns no refresh token. Its access token is signed with
`purpose=vault_maintenance`, reports `session_state` and can reach only the matching maintenance
operation. Erasure uses a recognizable disposable sentinel family because all ordinary families
are already revoked. Logout deletes that exact sentinel rather than updating an already revoked
row, making the presented bearer permanently invalid. Password reauthentication creates a new
recovery authority without reviving the old one.

## Quiescence and health

All three destructive operations take one process-wide maintenance mutex and the writer side of a
writer-priority activity gate. A queued writer prevents new readers from starving it. Both layers
are cancellation-safe. User searches and schedules are quiesced before mutation; managed-runtime
installation is joined through a real worker-completion event rather than task state alone.

The root response is static. `/health/live` performs no database or filesystem work.
`/health/ready` first attempts a reader lease and returns maintenance immediately if a writer owns
or awaits the gate; only an acquired lease starts the joined database, storage and migration probe.
Lifespan shutdown stops the scheduler before taking a background-task snapshot or cancelling work,
then waits for managed startup and worker shutdown in dependency order.

## Restore ownership and restart recovery

Restore derives exact destination paths from trusted fields rather than accepting archive paths:

- source documents use `assets/{sha[:2]}/{sha}`;
- profile photos use `assets/photos/{sha[:2]}/{sha}.jpg`;
- resume artifacts use `resumes/{profile}/{version}/{sha}.{format}`.

All UUID-backed string primary keys must be canonical lowercase hyphenated UUIDs. Path-like,
control-character, uppercase or alias identities fail before mutation. The archive is also bounded
to 128 MiB compressed, 256 MiB expanded, 5,000 members and 100,000 records.

Before the first absent destination is published, restore writes two checksummed journal copies at
`.restore/user-{id}`. The journal contains owner, archive fingerprint, sorted paths and monotonic
generation only. A newer torn-write copy is accepted only when owner/fingerprint match and its path
set is a superset; disagreement fails closed. Bytes stage inside the same owner namespace, are
fsynced and atomically promoted. Windows uses `MoveFileExW` with replace and write-through flags.

A restart accepts only the same archive fingerprint, clears stale owner staging and resumes
idempotently. If the ZIP is lost, erasure may supersede restore and remove published exclusive
bytes, staging and journal state. Startup cleanup is narrower: it removes only `.write-*` files
inside `assets` and `resumes`, never similarly named model or unrelated files.

## Rollback and privacy

Late failure rolls back database work, checks current bindings for every journal path, durably
unlinks only paths still exclusive to that recovery owner, clears the journal and runs SQLite
secure-delete/checkpoint/vacuum sanitation. If another account bound the same content-addressed
file after publication, that binding transfers ownership and rollback preserves the bytes.

`RestoreRolledBackError` is raised only after the complete cleanup invariant holds. The route then
uses one conditional state update to return `restore_pending` to `ready`, including on a restart
retry; the condition cannot overwrite a concurrent erasure state. Any incomplete cleanup instead
raises `RestoreCleanupPendingError`, retains `restore_pending` and returns an actionable same-ZIP
retry or erasure path. Successful restore revokes sessions and grants and imports schedules
disabled, requiring explicit user opt-in before automation resumes.

## Threat review

| Threat | Control |
| --- | --- |
| Crash after first file publication | Journal is durable first; same-fingerprint retry is idempotent |
| Original ZIP is unavailable | Complete erasure supersedes restore and owns staging/final cleanup |
| Different ZIP takes over recovery | Durable fingerprint mismatch fails closed |
| Journal primary is torn or corrupt | Redundant checksummed copies plus monotonic-superset validation |
| Rollback deletes another account's file | Current database bindings are checked before every journal unlink |
| Failed restore leaves recoverable SQLite text | Secure delete, checkpoint and vacuum before state clear |
| Login races reset | Owner-row serialization plus final family sweep |
| Recovery token opens ordinary workspace | Required signed purpose and lifecycle-specific dependencies |
| Logout appears to revoke erasure token but does not | Exact sentinel row is deleted; old bearer fails live-family lookup |
| Writer freezes desktop supervisor | Pure liveness and non-blocking readiness gate attempt |
| Crafted identities escape managed storage | Canonical UUID validation and server-derived exact paths |
| Startup cleanup traverses unrelated storage | Fixed asset/resume roots and `.write-*` filename filter |
| Archive or upload exhausts memory | Compressed/expanded/member/record limits and limit-plus-one upload reads |

## Adversarial findings closed

- Journal rollback originally treated every published path as still owned by the crashed account.
  It now preserves a path acquired by another account; a focused two-owner regression proves both
  byte survival and journal removal.
- The erasure sentinel was already marked revoked, so an update filtered to live rows made logout
  a no-op while the maintenance bearer remained valid. Logout now deletes that sentinel, and a
  password login must issue a distinct replacement before erasure can complete.
- Restore cleanup initially returned a restart retry to `ready` only when the current request had
  made the transition. A fully sanitized retry could therefore remain trapped in
  `restore_pending`. The wrapper invariant now permits an atomic conditional clear on every clean
  rollback; the hard-crash/late-failure/re-login regression proves convergence.
- Normal session issuance could use a stale ready owner after password verification, and reset
  could miss a family created after its first sweep. Locked re-read plus a final sweep close both
  sides of that race.
- Global `os.replace` mocking obscured the actual durability seam. Storage, restore journal and
  deletion now share an explicit durable replacement primitive, and fault tests patch that seam.

## Focused evidence

Journal copy, corruption, monotonicity, staging and cleanup tests passed 7 cases. Hard-crash,
lost-archive and SQLite/WAL sanitation passed 3 cases. The lifecycle/auth/health/runtime/migration
matrix passed 75 cases; bounded upload/auth/runtime coverage passed 68. Portability compatibility
passed 8 cases. The canonical UUID, shared-reference and atomic-storage selection passed 22 cases,
the complete atomic-storage file passed 18, the retry-from-pending/shared-reference regressions
passed 2, and static OpenAPI plus the purpose-aware dependency fixture passed 5.

## Known limits

- Process-wide gates rely on the supported single-sidecar topology. A future multi-writer service
  would need database/distributed coordination for reader leases as well as owner-row transitions.
- `fsync` and write-through requests cannot exceed the guarantees of the underlying filesystem,
  storage controller or sudden-power-loss environment.
- Portable ZIPs remain checksummed but neither encrypted nor authenticated. Store them under
  operating-system encryption and retry only archives from a trusted location.
