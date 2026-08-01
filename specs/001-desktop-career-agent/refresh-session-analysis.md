# Replay-detecting refresh-session analysis

## Purpose

CareerOS previously signed refresh JWTs without retaining server-side state. Logout removed the
browser cookie, but a copied token could still be replayed until its fourteen-day expiry. This
slice replaces that gap with restart-durable, single-use session families while keeping the
desktop and container login contracts local, bounded and migration-safe.

## Security boundary

- Every refresh JWT requires `exp`, `iat`, `jti`, `sid`, `sub` and `type`; access JWTs require
  `exp`, `iat`, `jti`, `sub` and `type`.
- `sid` is a non-secret 32-character family identifier. The database stores only the SHA-256
  digest of the family's current JTI, never a raw JWT or JTI.
- A successful refresh uses one compare-and-swap update over account, family, current digest,
  expiry and revocation state. The token keeps its `sid` and receives a new one-time JTI.
- A signed older token that observes a different current digest is replay evidence and revokes
  the whole family. In a two-connection race, one refresh may win the compare-and-swap, but the
  loser then revokes the family so the winner cannot continue refreshing.
- Logout revokes by the signed account/family binding. It therefore accepts either the current
  token or a still-valid already rotated token without accepting an unrelated family.
- Eight database-unique `(user_id, slot)` values bound persisted session metadata per account.
  Expired or revoked rows are reclaimed; concurrent slot collisions roll back and retry.
- Signed pre-migration refresh tokens have no `sid`, fail required-claim validation and trigger
  the existing canonical and legacy cookie clearing path.

## Lifecycle integration

Registration and login create a new bounded family after credential verification. Refresh rotates
that family before issuing a new access token. Logout revokes it before clearing all refresh-cookie
variants. A successful portable restore revokes only the restored account's active families, while
complete erasure removes only the erased account's rows. Portable export never contains session
rows, identifiers or digests.

These server-side operations do not create an access-token revocation list. An access token issued
before logout, replay detection, restore or erasure can therefore remain usable until the configured
short expiry, 30 minutes by default. A rejected refresh cannot extend that residual lifetime. An
installation signing-secret rotation remains the immediate all-token invalidation mechanism.

The renderer also treats a second `401` after a successful refresh as terminal. It emits the shared
unauthorized event and returns no private response, so stale authenticated UI cannot remain mounted
when server-side state rejects the retried access.

## Persistence and migration

`auth_sessions` contains only family id, owner id, bounded slot, current JTI digest, expiry,
revocation and timestamps. Its owner foreign key cascades, the digest is unique and the account-slot
pair is unique. The new revision follows the dossier-draft head, creates an empty table and performs
no unsafe backfill. Downgrade drops only this content-free authority table; upgrading again trusts
no historical refresh token and requires login.

Issue, rotation and revocation catch transaction failures, roll back and re-raise. Tests inject
commit failures into issue and rotation paths and assert that neither a partial row nor a partially
rotated digest survives.

## Threat review

| Threat | Control |
| --- | --- |
| Stolen refresh token reused after normal rotation | Digest mismatch revokes the entire signed family |
| Two refreshes consume one token concurrently | Database compare-and-swap admits one winner; the loser revokes the family |
| Logout receives a rotated browser cookie | Signed account and `sid` still identify and revoke the family |
| Database disclosure reveals usable credentials | Only one-way JTI digests and non-secret family metadata are stored |
| Repeated logins grow authority without bound | Eight unique account slots plus transactional collision retry |
| Upgrade accidentally trusts a stateless token | Required `sid` fails closed and every refresh-cookie variant is cleared |
| Restore or erasure affects a neighboring account | Every lifecycle mutation is owner-scoped and covered by two-user tests |
| Backup recreates live browser authority | Auth-session rows are excluded from portable export; restore revokes existing authority |
| Access token survives a refresh-family revoke | Explicit, bounded 30-minute default residual; rejected refresh never extends it |
| Retried protected request remains unauthorized | Shared frontend unauthorized event unmounts the private workspace |

## Review findings closed

- Full-suite edge tests still patched the removed route-level JWT decoder and expected a
  user-existence-specific error. They now patch the stateful rotation boundary and require the
  generic invalid-session response, avoiding an account-state oracle.
- SQLAlchemy's update result was too generic for the project-wide mypy gate. Explicit
  `CursorResult` casts and integer slot normalization close the typing gap without changing the
  transaction behavior.
- Duplicate native desktop session headers, unreadable ZIP members and control characters in log
  messages were adjacent trust-boundary findings. They now fail closed or normalize safely, with
  focused regressions.
- The supported Node prerequisite is now consistently documented and contract-tested as
  `>=24.18.0 <25`, matching `.nvmrc`, the package engine and the authoritative frontend run.

## Focused evidence

The security and migration matrices prove required-claim rejection, digest-only persistence,
sequential replay, logout with an old token, pre-migration rejection, the eight-slot cap, a real
two-connection SQLite race, transaction rollback, cross-user restore and erasure isolation,
portable-export exclusion, foreign-key cascade and migration downgrade/upgrade/head convergence.

The focused implementation run passed 47 backend tests. The extended auth, origin, migration,
portability, erasure and release matrix passed 168 tests. After the full-suite edge-test correction,
the auth route, service, replay and browser-origin matrix passed 77 tests. The focused frontend
session selection passed 41 tests, including terminal recovery after a refreshed retry returns
`401`. The final proportional backend rerun passed all 1,724 tests with four explicit opt-in
performance cases skipped.
