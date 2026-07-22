# Application readiness cross-artifact analysis

Date: 2026-07-22

Scope: deterministic Application Readiness Pack and the revision-safe preparation editor added for
CareerOS Local v1.2.0.

## Consistency review

| Artifact | Reviewed contract | Result |
| --- | --- | --- |
| Constitution | Local-first processing, inspectable deterministic output, durable artifact integrity, modal accessibility and content-free audit history | Aligned |
| Specification | FR-040–FR-045 and SC-014–SC-015 cover calculation, evidence, export, remediation, ownership, artifact bytes, reproducibility and keyboard behavior | Aligned |
| Plan | One bounded readiness service, canonical serializers, authenticated loopback routes, verified storage reads and a portal-backed modal; no schema migration | Aligned |
| Tasks | T106–T115 map specification, contracts, implementation, tests, UI and convergence without an unowned task | Complete |
| OpenAPI | Owned report/export reads and expected-revision preparation write describe all accepted fields and error states | Aligned |
| Backend | Nine stable weighted checks total 100 points; recorded PDF/DOCX files pass only after contained reads verify their digest and length | Aligned |
| Frontend | Application Detail is a labelled modal with dynamic focus containment, safe dismissal, opener restoration, responsive overscroll and complete corrective paths | Aligned |
| Tests | Zero-data, stale/foreign ownership, hostile Markdown, export digests, artifact failure modes, modal keyboard behavior, request races and edits are covered | Aligned |
| Demo and docs | The disposable seed produces a real published resume and a 100/100 application; the recorder opens that application and waits for the ready state | Aligned |

## Boundary checks

- Readiness reads only the authenticated user's application, profile and owned immutable resume
  version. A foreign application or resume is reported as not found or rejected.
- The calculation contains no inference client, provider call, telemetry path or wall-clock-derived
  score. Unchanged source revisions produce the same report and export bytes.
- The response and exports omit raw role descriptions, local storage paths, session credentials and
  resume contents. Markdown escapes user-controlled text before rendering.
- Artifact rows are not treated as proof. Every recorded PDF or DOCX is resolved inside the data
  root, read, hashed and length-checked. Deleted, corrupt, unreadable, escaping or truncated files
  block readiness and reveal only their format name.
- The preparation write performs a conditional update against the expected revision and records only
  sorted changed field names. It can repair every editor-routed blocker: role title, company,
  description, route and linked published resume.
- The score's nine even weights make warning credit exactly half of the available points without
  floating-point rounding.
- The portal keeps modal content outside the inert application background. Focusable descendants
  are queried on every Tab press, so controls inserted by the editor cannot escape the trap; cleanup
  restores the exact prior scroll state and connected opener.

## Findings resolved during analysis

1. `capture_role_identity` originally opened an editor that did not expose title or company. Both
   fields are now included in the schema, OpenAPI contract, conditional write, UI and tests.
2. Application email validation now uses one trimmed, case-normalized parser for create and update
   paths rather than permissive substring checks.
3. Canonical Markdown now escapes HTML and Markdown control characters, preventing stored role names
   from injecting links, headings or script-like markup into downloaded reports.
4. The Windows demo recorder now waits for child termination and retries bounded temporary-directory
   cleanup, eliminating the observed post-publication race.
5. Resume-artifact readiness originally trusted database rows. It now verifies contained durable
   bytes against both immutable SHA-256 and declared length, with adversarial failure coverage.
6. Application Detail originally looked like a drawer but did not own modal semantics or focus.
   It now uses a portal, labelled dialog, dynamic trap, inert/scroll lock, Escape and focus return.
7. Detail reads and post-write board refreshes originally allowed stale responses or could tear down
   the modal. They now use latest-request-wins cancellation and a non-blocking refresh; stage choices
   are derived from the updated application before a second write.
8. User-facing locality copy originally denied any network request even though the UI uses an
   authenticated loopback API. It now states the precise boundary: no model or external service.

No unresolved requirement contradiction, orphaned task or undocumented persistent-data change was
found. The remaining release actions are remote CI, native matrix rehearsal, signing and authorized
tag publication; they are not implementation gaps in this feature.
