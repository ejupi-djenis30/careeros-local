# Live access-family authority convergence

## Scope

This review closes Phase 26 task T205 by aligning FR-089, SC-032 and the current constitution with
live access-family lookup, atomic logout, deterministic renderer identity, browser-origin handling
and the exact Node runtime preflight. The subsequent vault-lifecycle phase extends—rather than
weakens—the contract with purpose-bound maintenance authority.

## Requirement mapping

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Stable access/refresh family | Pair issuance and rotation under one `sid` | Claim decode and rotation assertions |
| Live access authority | Indexed AuthSession/User lookup on each protected request | Logout, replay, restore and erasure access rejection |
| Signing failure safety | Generate replacements before persistence/CAS | Injected access-generation failures preserve row/digest |
| Atomic multi-family logout | Valid cookie/bearer union in one transaction | Two-family success and commit rollback |
| Truthful logout failure | `503`, cookie clearing, unmounted workspace and explicit bearer retry | Backend response and renderer failure/retry tests |
| Deterministic identity | Client epoch around login, register and refresh | Overlap tests prove last-started-wins |
| Terminal refreshed retry | Shared unauthorized event on second `401` | Client and AuthContext regressions |
| Browser missing-Origin boundary | Exact Fetch Metadata acceptance matrix | Same-origin, hostile, duplicate and native omission cases |
| Exact supported Node | Engine strictness plus every-script preflight | Node 24.18 floor, upper bound and manifest enumeration |
| Recovery purpose isolation | Access `purpose` and lifecycle-specific dependencies | Purpose-less/maintenance ordinary-route rejection |

## Cross-artifact findings

- FR-089 and SC-032 match the existing `AuthSession` schema: no access-token table or access-JTI
  blacklist was introduced.
- OpenAPI describes the same refresh family and logout endpoints; the lifecycle addition exposes
  optional login `session_state` only for maintenance access.
- Privacy guidance states the in-flight request boundary accurately: committed revocation denies
  later authorization but cannot cancel work already admitted.
- Cookie, Origin, Fetch Metadata and desktop-session controls remain layered. Native callers may
  omit browser headers, but they do not bypass the native per-launch secret in desktop mode.
- Every public executable frontend command is discovered by the Node manifest test and routes
  through the exact `>=24.18.0 <25` check.
- The stale unit dependency fixture was updated to include `purpose=session`; production decoding
  continues to reject purpose-less access JWTs rather than adding compatibility.

## Final validation

| Gate | Result |
| --- | --- |
| Complete backend regression | 1,791 passed and four explicit performance cases skipped; zero failures |
| Branch coverage evidence | 81.04%, above the required 80% threshold |
| Refresh-family unit file | 16 passed, including the eight-slot bound and real refresh race |
| Purpose-aware dependency and static OpenAPI | 5 passed |
| Full Ruff and mypy | Passed; final changed main/journal/tests also passed focused reruns |
| Exact Node manifest preflight | 4 passed under Node 24.18.0 |
| Rust desktop follow-up | Format/Clippy passed and 19 tests passed; cargo-deny has no vulnerability or unsound diagnostic after `event-listener` 5.4.2 |

The coverage-bearing run initially exposed 16 stale scheduler/search fixtures whose mocked owner
had no lifecycle state. They were corrected to model `ready`; the affected 102 tests and the final
complete suite passed. No production compatibility was added for missing state or purpose.

## Result boundary

The implementation and active specification converge without new bearer persistence or a widened
network boundary. Commit, protected-branch CI, signed installers and deployment remain outside this
local task. Exact full-gate evidence is shared with the vault-lifecycle convergence because both
slices are exercised by the same final backend, type, lint and Node runs.
