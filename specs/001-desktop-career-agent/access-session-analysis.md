# Live access-family authority analysis

## Purpose

The replay-detecting refresh slice made refresh JWTs single-use, but an access JWT could still
authorize new requests until its own expiry after the family was revoked. Phase T makes the
existing bounded `AuthSession` row the live authority for both bearers, without persisting access
tokens, access JTIs or a second blacklist. The later vault-lifecycle slice adds a required signed
purpose so recovery authority cannot be confused with ordinary workspace access.

## Authority contract

Access and refresh JWTs require `exp`, `iat`, `jti`, `sid`, `sub` and `type`; access additionally
requires `purpose`. Normal access has `purpose=session`; recovery access has
`purpose=vault_maintenance` and no refresh token. Both normal bearers share the same non-secret
family id. Every protected request validates the JWT
and then performs an indexed join over family id, signed subject, owner, expiry, revocation and
`ready` lifecycle state. A self-consistent signed JWT is therefore insufficient after a committed
logout, replay response, restore or erasure.

Refresh rotation generates both replacement bearers before its compare-and-swap. A signing failure
cannot consume the old credential. A replay loser revokes the family, so even the winner's newly
issued access token fails on its next protected request. Work authorized before a revoke commit may
finish; CareerOS does not claim retroactive cancellation.

## Atomic logout and renderer behavior

Logout validates the refresh cookie and optional access bearer independently, takes their distinct
owned family union and revokes it in one transaction. A rotated old cookie can still identify its
family. Commit failure rolls every revocation back, clears all refresh-cookie variants, returns a
content-free `503` and leaves only the access bearer in renderer memory for an explicit retry.
The private workspace unmounts before that retry and is never replaced by a false logged-out login
screen. Vault erasure's already-revoked recovery sentinel is deleted exactly on logout.

Login, registration and refresh use a monotonically changing client epoch. A late response from an
older identity transition cannot overwrite a newer session. A second protected `401` after one
successful refresh is terminal and broadcasts the common unauthorized event.

## Browser and runtime boundary

When `Origin` is present, auth mutations require one exact configured local origin. When it is
absent but browser Fetch Metadata is present, only one canonical `Sec-Fetch-Site: same-origin`
value is accepted. Native and CLI callers that omit both remain supported. Refresh cookies are
HttpOnly, scoped to `/api/v1/auth` and cleared at both current and historical paths.

The supported JavaScript runtime is exactly Node `>=24.18.0 <25`, with engine strictness. Every
public npm command that executes Node, Vite, Playwright or Tauri has a matching fail-fast preflight;
the manifest test enumerates scripts so new commands cannot silently bypass it.

## Threat review

| Threat | Control |
| --- | --- |
| Access JWT reused after logout | Live family lookup observes committed revocation |
| Replay winner keeps its access token | Loser's family revoke invalidates winner at next request |
| Two presented logout families partially revoke | One transaction over the validated distinct union |
| Logout commit fails but UI claims success | Rollback, cookie clearing, unmounted workspace and explicit bearer retry |
| Late login replaces a newer identity | Client epoch makes account transitions last-started-wins |
| Missing Origin bypass from another browser context | Fail-closed Fetch Metadata matrix |
| Native caller rejected for lacking browser headers | Omission of both remains the explicit native contract |
| Maintenance bearer reads ordinary data | Required purpose plus durable lifecycle-specific dependency |
| Raw bearer becomes recoverable at rest | Only family metadata and current refresh-JTI digest persist |
| Unsupported Node starts a partial build/test | Exact preflight precedes every executable public script |

## Cross-slice findings closed

- Logout errors originally risked exposing login controls while the server family remained live;
  the workspace now stays unmounted and offers an explicit retry.
- Client overlap could allow a slow prior login or refresh to replace a newer identity; epochs make
  every account transition deterministic.
- Browser auth mutations with no Origin needed a second signal. The Fetch Metadata matrix rejects
  hostile browser contexts without breaking native requests.
- The original unit dependency fixture modeled only subject and family. It now includes the
  mandatory `purpose=session`, preserving fail-closed behavior for older purpose-less access JWTs.
- Pending vault maintenance made a live family ambiguous. Purpose-bound access plus lifecycle state
  now separates normal and recovery authority without a new token table.

## Verification scope

The auth matrix covers claim rejection, stable family binding, logout/replay/restore/erasure
invalidation, two-connection refresh races, multi-family rollback, explicit logout retry,
pre-migration rejection, bounded slots and transaction failures. Renderer tests cover overlapping
login/register/refresh operations, terminal second-`401` handling, cookie-clearing failure and
workspace unmount. The Node manifest test covers the exact lower/upper runtime range and every
public executable script.
