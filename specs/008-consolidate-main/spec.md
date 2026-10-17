# Specification: Consolidate all work into main

Date: 2026-10-17. Status: baseline integrated; follow-up locally verified.
Owner request: integrate all branches into main, remove branches, clean the
project and make the combined application work.
Follow-up request: continue the refactor, cleanup and correction of confirmed
anomalies after the verified main integration.

## Outcomes

1. Preserve the verified refactor and every branch's useful behavior. Previously
   integrated or superseded work must not regress current security, schema,
   frontend navigation, dependencies or authority boundaries.
2. Recover configurable job providers from the older provider/parity branch,
   integrating its desktop UI, authenticated APIs, explicit acquisition consent,
   persistence and portability into the current architecture. Preserve current
   proposal-only external-agent authority and authenticated desktop bridge.
3. Integrate installable dependency/image/workflow updates and preserve newer
   security fixes. Record unavailable versions and failed gates exactly.
4. Main is the sole remaining local and remote branch after successful integration.
   Retain a verified Git bundle before deletion, map every original branch tip to
   its integration decision, and respect protected-main rules and required checks.
5. Correct independently reproduced post-integration failures in private
   diagnostics, malformed-archive handling, provider mutation acknowledgement and
   stored-photo reuse. Preserve the verified baseline and record its completed
   execution separately from the new work.

## Requirements

- FR-001 Commit the already reviewed refactor without losing any work; inventory
  all local/remote branches and open PRs before mutation or deletion.
- FR-002 Assess branch content against the current application, distinguishing
  equivalent, superseded and genuinely missing work with recorded evidence.
  Recheck remote tips immediately before deletion. Preserve and assess automated
  follow-up branches created during cleanup, integrating compatible updates
  through the same checks before removing their refs.
- FR-003 Add configurable providers without restoring direct external-agent
  publication, fact confirmation, standalone writable vault access or old grants.
  Provider HTTP access remains explicit, authenticated, consented and subject to
  bounded request/response and network validation.
- FR-004 Add any provider persistence through a uniquely identified Alembic
  migration based on the current head. Include export/import/reset/erasure,
  rollback and cross-account isolation contracts.
  A provider-only account without a career profile must remain exportable and
  restorable without synthesizing a profile or career facts. Version 9 may omit
  the profile only when profile-owned relationships are empty and concrete owned
  provider records exist; legacy archive invariants remain unchanged.
  Commit-outcome verification must compare the complete restored provider
  inventory, owner, content and timestamps. Positive fixtures must reconstruct
  the actual restored state, including explicit archived timestamps; ordinary
  ORM edits must not be mistaken for proof of an identical restore.
- FR-005 Integrate compatible installable updates with regenerated hash locks and
  complete notices. Keep newer security fixes over obsolete branch pins; do not
  introduce unavailable packages, mismatched runtime binaries, audit suppression
  or weakened gates.
  Vendor upgrades must preserve the no-telemetry boundary even when ambient
  tracing providers or auto-configuration environment variables are present.
- FR-006 Preserve main's signed, linear, review/check-protected integration path.
  Do not disable protection or force-push. Push and merge the concrete combined
  result through the permitted path; only then remove integrated branch refs.
- FR-007 Verify the combined backend/frontend/native application, migration
  roundtrip, focused provider/security/portability regressions, artifact contracts
  and a real API journey. Record unexecuted or failed environment/release gates.
- FR-008 Keep personal vaults and ../Career untouched, clean only inventoried
  generated material, preserve development infrastructure, and leave a clean Git
  worktree. No release publication or new release tag is authorized.
- FR-009 Private diagnostic redaction must cover actual ASGI server logging in
  desktop and container startup, including non-propagating Uvicorn handlers and
  exception records. Server configuration must not reinstall an unprotected
  output path; no raw exception text, traceback or private sentinel is emitted.
- FR-010 A confirmed provider mutation must immediately update local identifier,
  revision, enabled state and redacted editor data. A subsequent catalog refresh
  failure must preserve that acknowledgement and accurately distinguish refresh
  failure from a failed write. Never repeat a write automatically or retain a
  deleted provider as the selected saved record. Imported provider packs and
  user-selected documents retain their confirmed counts through refresh failure
  without inventing catalog records absent from the server response.
- FR-011 Reusing a stored profile photo must verify owned normalized metadata and
  contained bytes against digest and length before claiming upload success or
  changing the selected photo/profile revision. Missing, corrupt or invalid
  stored content fails closed without overwriting it; healthy reuse stays
  idempotent and preserves shared-file and commit-recovery boundaries.
- FR-012 Malformed ZIP metadata and invalid compressed backup members must produce a bounded archive
  validation error through inspect and restore. Decoder failures must not escape
  as internal errors or strand an otherwise ready vault in restore-pending;
  preserve manifest, path, size, relationship, lock and rollback validation.

## Success criteria

- SC-001 Every original branch tip has a recorded preserved/superseded/integrated
  disposition backed by a verified recovery bundle and content assessment.
- SC-002 Provider CRUD/testing/acquisition and UI pass current authentication,
  consent, network isolation, concurrent revision and account isolation tests.
- SC-003 Provider backup/restore/erasure and forward/back migration contracts pass;
  the existing migration graph has one unambiguous head and no revision collision.
- SC-004 All required quality/security/license gates have exact results. A failed
  vulnerability scan or unavailable fixed version remains an explicit blocker.
- SC-005 The integrated main is published without bypassing protections; no other
  branch refs remain once their content is safely integrated. If enforced checks
  prevent publication/deletion, report the exact blocked action and retain work.
- SC-006 No private content, secret, temporary command output or silent installer
  is added, and deterministic vault workflows remain usable without inference.
- SC-007 Real Uvicorn configurations and synthetic ASGI exceptions prove that
  diagnostic output contains neither private sentinels nor raw tracebacks, while
  safe content-free diagnostics remain available in supported startup modes.
- SC-008 Create/update/delete/toggle/import regressions with a successful write followed
  by a failed catalog read preserve the committed state, redaction and correct
  next request. Unmount, cancellation and actual write errors remain correctly
  handled without discarding newer editor data.
- SC-009 Re-upload regressions reject missing/corrupt/unusable stored-photo
  metadata without selecting that asset or advancing profile revision. A valid
  duplicate remains reusable without an extra asset or revision.
- SC-010 A valid bounded ZIP control remains inspectable/restorable; a corrupted
  compressed member returns the expected validation response, preserves existing
  records and leaves or returns the vault to its prior safe lifecycle state.

## Governing constraints

Constitution 2.0.1 is unchanged. The old branch's constitution, direct agent write
tools and publication model are superseded by current governing constraints.
Passing source tests is not approval of a production release or native installer.
