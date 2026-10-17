# Specification: Consolidate all work into main

Date: 2026-10-17. Status: signed baseline integrated; UI source locally verified.
Owner request: integrate all branches into main, remove branches, clean the
project and make the combined application work.
Follow-up request: continue the refactor, cleanup and correction of confirmed
anomalies after the verified main integration.
Further request: continue the refactor including the UI, from signed main cdc91c1.

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
6. Refactor UI controllers and shared modal behavior around explicit ownership.
   Preserve newer selections and drafts across delayed operations, keep filtered
   projections coherent, and provide accessible dialogs and content-free error
   diagnostics without changing career truth, appearance or agent authority.

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
- FR-013 Renderer-owned error diagnostics must contain only allowlisted operation
  codes, including React caught/uncaught/recoverable callbacks and explicit
  service failure logs. Never forward errors, stacks, identifiers or request/data
  payloads to the console. Preserve translated error views and recovery actions.
- FR-014 Coach conversation loads and sends must belong to the currently active
  conversation/operation. Late success or error must not replace a newer
  selection, reopen a cleared conversation or erase a later composer draft.
  Real errors remain visible and retryable; model readiness and explicit context
  stay mandatory. Separate request ownership from page rendering.
- FR-015 Modal content workflows must share topmost keyboard ownership, focus
  containment and background/scroll isolation. Nested and out-of-order cleanup
  must preserve remaining dialogs; restore original inert/ARIA/overflow state
  and appropriate connected focus targets only when ownership permits.
- FR-016 An acknowledged application update must reconcile its board record
  without selecting another dossier, reopening a closed dialog or regressing a
  newer revision. Closing a dossier must invalidate its pending detail read;
  creation acknowledgements must respect the current selection and creation-form
  session, preserving a newly reopened form and its newer draft. Split workspace
  orchestration from page composition, retaining
  current event history, filtering, account isolation and explicit publication.
- FR-017 Jobs mutation/undo acknowledgements must not edit rows or counts from a
  different active filter/page context. Reconcile the current projection through
  its current query, retaining existing error, toast and undo behavior without
  injecting a record that does not satisfy the active filter.

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
- SC-011 Synthetic private errors, component stacks and job identifiers never
  appear in renderer diagnostic calls; real React root callbacks and entry-point
  wiring are covered, and translated error fallback/reload remains functional.
- SC-012 Out-of-order coach loads, conversation changes during send, later typed
  drafts, cancellation/unmount, actual errors and retries have regression tests.
- SC-013 Real dialog overlap tests prove only the top closes on Escape, the
  background stays inert and scrolling stays locked until the last modal closes.
  Preserve initial/return focus, hidden/disabled-control handling and existing
  keyboard, responsive and accessibility acceptance for every migrated dialog.
- SC-014 A delayed application-A update while B is selected or no dialog is open
  never changes that selection; stale revisions never overwrite newer state.
  A pending detail read cannot reopen a closed dossier, and a delayed creation
  cannot overwrite a later selection or clear a newly reopened form/draft.
- SC-015 A delayed dismiss/undo from filter A after switching to B preserves B's
  valid rows/counts, with current-query reconciliation and error controls covered.

## Governing constraints

Constitution 2.0.1 is unchanged. The old branch's constitution, direct agent write
tools and publication model are superseded by current governing constraints.
Passing source tests is not approval of a production release or native installer.
