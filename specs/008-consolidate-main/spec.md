# Specification: Consolidate all work into main

Date: 2026-10-17. Status: implementation.
Owner request: integrate all branches into main, remove branches, clean the
project and make the combined application work.

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

## Governing constraints

Constitution 2.0.1 is unchanged. The old branch's constitution, direct agent write
tools and publication model are superseded by current governing constraints.
Passing source tests is not approval of a production release or native installer.
