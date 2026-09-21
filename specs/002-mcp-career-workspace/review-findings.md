# Implementation Review Notes — Feature 002

**Status (2026-09-13): closed after pre-merge correction and independent re-review.** This file
preserves the reproducible findings from the interrupted implementation as an audit trail.
R001–R042, RT001–RT016, RA000–RA014 and RR001–RR009 were all corrected and covered by regression
tests. The owner's later instruction authorized the coordinating Codex agent and its subagents to
implement corrections directly after Antigravity/Spark quota exhaustion.

The final independent security/integrity review found no significant open issue. Its focused
reruns passed 145 portability cases, 133 agent/desktop/workspace MCP cases, 38 final descriptor and
vault cases, and a 121-case independent MCP audit with Ruff. The coordinator's complete gate passed
2581 backend tests with the declared platform/performance skips, then passed all four opt-in
performance tests. Full frontend, Rust, migration, packaged-sidecar and visual evidence is recorded
in `validation.md`. The findings below describe their original failure state and are no longer
instructions for unfinished work.

The owner-requested pre-merge audit subsequently found PM001 preset/locale inconsistency, PM002
accepted-external analysis snapshot quarantine, PM003 missing CLI disclosure propagation, PM004
duplicate-key parsing in nested packet manifests and PM005 a personal absolute path in validation
evidence. T067–T071 closed those categories. Independent re-review then found and closed a
version-without-preset and empty-preset edge case within PM001, and reported zero remaining P0–P2
findings. The frozen-tree backend, frontend, native, migration, sidecar and performance gates all
passed after the corrections.

## Agent context and contracts

- R001: context.py currently includes every confirmed fact type, including private reference
  material, and recursively redacts dictionaries but leaves dictionaries inside lists unchanged.
  Enforce the selected safe fact/attribute policy with nested-contact and private-reference tests.
- R002: context.py truncates strings/lists/fact count without always declaring truncation and
  only reduces to 20 facts once when above MAX_CONTEXT_BYTES; it can still return oversized
  data. Reject remaining oversize and do not silently lose explicitly selected evidence.
- R003: Recheck target existence/ownership and all destination revisions (including dossier)
  before snapshot and acceptance. context.py initially tolerates missing target IDs and
  omits dossier revision; a surrounding service may fix this, so inspect completed code.
- R004: schemas.py initially allows discovery without source URL/gates/scores and accepts
  materials as arbitrary dictionaries. Final strict result contract must reject missing
  provenance/evidence; material handling must fail closed until typed validation is implemented.
- R005: Apply fit-v1 weights/unknown-gate policy from updated data-model.md and add golden
  fixtures; an external overall score must not override rejection or unknown mandatory evidence.
- R013: Empty selected_fact_ids currently skips the filter and exports every confirmed fact.
  Distinguish an omitted selection from an explicit empty selection; never broaden disclosure.
- R014: Context reads noncanonical preference names and drops preferred_languages,
  preferred_locations, available_from, notice_period_days, commute/work-mode/workload constraints.
  Preserve actual CareerPreferences fields and test their impact on the fit policy.
- R015: A materials request targeting an application omits Application.job_snapshot unless
  target_job_id is separately supplied. Bind and include the selected application's advert.
- R016: Untargeted analysis currently supplies ten jobs but has one unidentifiable result.
  Require a single owned target for analyze; discovery is the multi-opportunity workflow.
- R017: Phone redaction corrupts approved dates and metrics (2019-2024, Budget EUR 250000).
  Use field-sensitive contact redaction, retaining substantive evidence and nested protection.
- R018: Creation accepts thousands of malformed fact IDs and unbounded preset IDs. Enforce
  UUIDs, uniqueness/count/string bounds and the catalog's preset/version/locale combination.
- R019: Cancel/reject use ORM read-then-write rather than database CAS, and expiry does not
  increment revision. Test concurrent terminal transitions and reject obsolete row updates.
- R024: submit_proposal only checks the echoed frozen input digest, not current profile/job/
  application/CV/dossier revisions or live confirmed facts. Revalidate before any write.
- R025: get_work_result permits another or expired grant belonging to the same user to read
  receipts, without bound-grant/scope/maintenance checks. Validate every operation consistently.
- R026: Claim grounding checks only citation membership. An invented doctorate/date/metric
  passes when citing Basic programming. Reuse substantive grounding and negative golden cases.
- R027: A rejecting gate only blocks strong_fit; consider passes and sets worth_applying=True.
  Empty quote references also pass. Reject/unknown gates must dominate all recommendations.
- R028: Acceptance omits work/grant expiry and materials falls through to accepted with zero
  material writes. Fail closed until complete; include all target revisions and atomic rollback.
- R029: Submission and acceptance also lack database CAS. Concurrent identical submissions
  may raise a raw uniqueness error, and terminal states may resurrect. Test two real sessions.
- R030: Identical submission retry after acceptance fails before looking up its original
  receipt. Preserve authenticated idempotency for identical key/payload and reject conflicts.
- R031: Submission DTO request_id can differ from the route/request argument without rejection.
  Bind identities exactly or remove duplicate identity from the wire contract consistently.
- R032: Discovery acceptance drops observed_at/source provenance and listing gate/score result;
  it invents a URL when absent. Require real source URL and retain useful observed analysis in
  canonical owned opportunity snapshots, without allowing client-selected provider namespaces.
- R033: DesktopBridgeClient interpolates unvalidated request_id into URL; traversal with query
  syntax sends the grant to /api/v1/auth/login. Require canonical UUID IDs and fixed routes;
  test traversal/query/fragment/encoded separators before any HTTP request occurs.
- R034: client.request buffers the entire response before checking MAX_RESULT_BYTES; a 786432
  byte stream is fully read before rejection. Stream and count actual decoded bytes under the
  cap, bound outgoing payloads before network IO and preserve total request deadlines.
- R035: MCP ToolError can include a synthetic bearer from backend/protocol error text. Never
  propagate untrusted server messages/exception repr; return a fixed safe code/message and
  test every error path with secret/context sentinel strings absent from stdout/stderr/errors.
- R036: All six MCP output schemas are generic additionalProperties:true; result input lacks
  the discover/analyze/material discriminated schema, and returned context contains no usable
  proposal schema. Expose strict versioned schemas/instructions so real clients can produce
  conforming proposals without reading implementation code. Test via actual SDK tool listing.
- R037: Global pytest conftest bypasses local-analysis readiness and uses one StaticPool
  in-memory connection. Initial agent route tests therefore do not prove no-model behavior
  with real guards or independent-connection CAS. Add real migrated file-SQLite integration
  and actual backend/lease/MCP-session tests; SDK memory + mocked HTTP alone is insufficient.
- R038: DesktopSessionMiddleware exempts the entire /agent-bridge prefix, including DELETE
  status and POST arbitrary-admin. Restrict exact supported method/path shapes with canonical
  UUIDs, rejecting all other requests without desktop session authority.
- R039: Bridge currently accepts a non-loopback ASGI peer and foreign Origin with local Host.
  Enforce peer/origin/host separately before grant access, retaining no-store/nosniff errors.
- R040: proposals:write-only bridge list reveals private instruction text without context:read;
  use a separate metadata projection or require the context scope for detailed list fields.
- R041: get_work_context returns frozen context after cancellation/expiry. Check current work
  lifecycle on reads, not merely grant validity. Revoke/expiry/maintenance tests must reach the
  actual boundary, not a mock transport that bypasses auth/guards.
- R042: Canonical URL validator silently accepts localhost, empty userinfo, semicolon params,
  empty query/fragment delimiters and noncanonical ports; invalid port ranges raise raw errors.
  Require the exact documented numeric-loopback URL form and safe structured failures.

## Reference and application implementation review

- RA000 (startup blocker): Partial letters.py imports nonexistent extract_safe_links,
  is_safe_link_url and get_preset. backend.main cannot import, so current full pytest aborts
  before collection. Align actual public APIs first; do not invent facade names or stub them.
  Current mypy also flags nonexistent ResumeDraft.user_id: ownership is through CandidateProfile.
  Publication also calls sanitize_application_snapshot without its mandatory quarantine_reason,
  causing a runtime TypeError beyond the import failures. Verify real public signatures.

- RR001: New reference DOCX traversal repeats id(cell._tc) proxy deduplication, risking omitted
  cells as Python IDs recycle. Keep actual nodes/deduplicate real merges and reject depth above
  bound instead of silently returning without reporting lost content.
- RR002: Goal numeric parsing extracts digits from invalid values: workload_min=-20 becomes20,
  notice_period_days=-5 becomes5, workload_min=25.5 becomes25 and distance=-10 becomes10.
  Parse whole documented syntax, preserve signs, reject invalid values and do not guess.
- RA001: Initial application-material migration downgrade drops draft-binding columns then
  restores NOT NULL version_id even with unpublished bound drafts. Define an explicit safe
  downgrade policy, test populated downgrade/re-upgrade and preserve older publications; never
  invent/publish a CV to satisfy downgrade and never orphan enhanced packet bytes silently.
- RA002: Migration lacks the binding CHECK present in ORM metadata; resume_draft_id SET NULL
  contradicts the exactly-one binding constraint. Align migrated/metadata DB constraints and
  define valid draft deletion behavior, testing actual populated SQLite migration and deletion.
- RA003: render_letter_pdf builds the same mutable story twice into one buffer. The second
  build sees an exhausted story; isolated review (temporary in-memory aliases for known missing
  imports only) produced zero PDF pages and no body text, with invalid object-offset warnings.
  Build once, count/parse the actual result and validate every required visible field.
- RA004: _format_links_for_reportlab escapes the whole string only when no URL is found.
  With a link it retains raw surrounding markup; a probe preserved an input <b> tag. Escape
  all text fragments and attributes independently, then insert only validated link markup;
  test that image/resource tags cannot cause file or network access during rendering.
- RA005: Email publication validation accepts recipient 'not an email', a subject containing
  U+0001 and attachment ' resume.pdf ' while actual file is resume.pdf. Validate full mailbox/
  header grammar and bounded canonical attachment names, preserving exactly the checked names
  in generated EML/checklist. Current isolated probes generated both artifacts for all cases.
- RA006: dossier publication puts commit and journal cleanup in one try/rollback handler.
  If commit succeeds but its acknowledgement is lost, or only journal deletion fails, the
  handler deletes the committed ZIP. Two isolated AST probes confirmed committed=True and
  packet_deleted=True. Resolve uncertain outcomes and separate post-commit cleanup from rollback.
- RA007: packet rollback suppresses failed unlink and still removes its recovery journal
  (isolated probe confirmed). Store runs outside rollback handling; no journal reconciler exists;
  rollback ignores the created flag and committed bindings. Recover under the vault lock with
  ownership/identity checks; retain journal evidence until cleanup is actually complete.
- RA008: The flush-only dossier method performs loaded-object revision comparison without
  database CAS. A temporary file-SQLite/two-Session probe saved both revision-1 edits and ended
  at revision 2 with the first edit lost. Application/CV checks have the same pre-write weakness.
  It also calls db.rollback internally, violating the enclosing acceptance transaction's control.
- RA009: Publishing a draft-bound dossier falls back to the already linked version without
  explicit selection and compares version.profile_revision with resume_draft_revision, unrelated
  counters. An older version from the same draft may pass. Prove exact approved draft/version
  correspondence and current binding instead of accepting matching incidental counters.
- RA010: Readiness is computed before replacing application.resume_version_id with the selected
  version. A first explicitly selected CV can be blocked, or an older CV's score/fingerprint can
  approve a packet containing another version. Validate readiness against the actual selection.
- RA011: Publication compares only four legacy draft fields. letter_options, email_draft and
  generation_provenance can change in the publish POST without another draft save/review. Compare
  the entire canonical publishable payload and all relevant revisions before generating bytes.
- RA012: dossier_service defines new ApplicationNotFoundError/Conflict/Validation classes distinct
  from the ones exported by service.py and caught by routes. Domain 404/409/422 errors become500.
  Preserve shared public exception identities and verify responses through actual owner routes.
- RA013: Packet download dispatches on artifact-row presence instead of dossier event schema.
  An isolated schema-3/missing-row probe took the legacy reconstruction path. Schema 3 must fail
  visibly on missing/corrupt artifacts and validate event/manifest/artifact identity together;
  schemas 1/2 must always retain their historical reconstruction path.
- RA014: Letter export reads identity/contact fields from the snapshot root, while CV publication
  stores them under snapshot.profile with display_name. Use the actual saved snapshot contract
  and assert every selected sender/contact field in extracted PDF/DOCX content.
- RR003: Accepting a preference while profile save is pending is allowed, but the late save
  response replaces the full editor and dirty flag. Current handlers reproduced saved Developer,
  accepted Logistics, then response revision2 removing Logistics and declaring clean. Preserve
  later edits or prevent conflicting acceptance; test deferred saves with real component handlers.
- RR004: Combined list preferences are not validated as a whole. Existing 50 roles plus one
  accepted candidate produces a claimed successful editor mutation but the real CareerPreferences
  DTO rejects51. Validate the entire resulting DTO before any mutation and preserve prior edits.
- RR005: Source role/file stay editable during upload, without request identity. Current handlers
  reproduced pending GoalA/goals, selection StoryB/narrative, then late A clearing StoryB and
  showing GoalA under the narrative selector. Reject stale replies or disable conflicting controls.
- RR006: Failed preference acceptance clears selected candidates; a later valid acceptance leaves
  the previous conflict error visible. Preserve selection on failure and clear/update its error
  after success, including workload80/max60 rejected then workload40 accepted.
- RR007: 51 unrecognized goal lines produce51 review_notes; SourceDocumentResponse allows50 and
  raises an uncaught ValidationError. Bound notes with a visible omission summary before storage
  and response validation. A valid bounded import must not fail only due to explanation count.
- RR008: Conflicting scalar candidates workload_min80 and20 are both accepted and counted while
  silently keeping20. Require a visible choice and show scalar replacement versus list merging
  against the editor's current value; reject unresolved conflicts before changing preferences.
- RR009: Recognized numeric fields with unrecognized values (workload min: several, notice
  period days: later, max distance: nearby) produce no candidates, notes or warnings. Explain
  unsupported values rather than silently dropping them; this is separate from RR002 coercion.

Read-only packet characterization found the updated isolated ZIP builder retains identical
bytes/manifests to HEAD for synthetic schema 1.0 and2.0 fixtures. This is positive builder-only
evidence, not endpoint validation while RA000 prevents bootstrap. The current failing frontend
test at CareerProfilePage.test.jsx:327 selects the first page checkbox (a preference-editor
control), not its intended candidate; scope by accessible name/container without weakening the
acceptance assertion. That fixture failure alone does not prove the normal acceptance path fails.

## UI integration

- R006: agentAccessModel.getCanonicalDesktopUrl initially guesses ports from window location
  and accepts non-loopback/https/arbitrary paths. Installed mode must use actual verified backend
  config and distributed launcher; developer config must be explicitly labeled and validated.
- R007: agentWorkModel.filterWork initially reads instructions/kind but backend schema uses
  instruction/work_kind. CreateWorkDialog also posts kind/instructions, ProposalReview reads
  result/client/model/vacancies instead of payload/client_label/model_label/listings. Verify
  exact backend/frontend DTO integration with actual serialized schemas, not mock-only tests.
- R008: Newly added grant disclosure field must flow from explicit UI action through
  GrantIssueRequest. Review API and UI currently edited independently before integration closure.
- R009: CreateWorkDialog implements its own focus trap but initially does not mark the background
  inert and silently turns grant-load failure into an empty list. Reuse the existing modal
  isolation pattern, retain actionable errors and test stale async request cleanup.
- R010: AgentWorkService.rejectWork unconditionally adds reason, but the strict server CAS DTO
  rejects that field. Every rejection must be tested against the actual route contract.
- R011: AgentWorkPage does not cancel/version getWork across modal opens, and onUpdateWork may
  replace work B with a late response for A while retaining B's proposal. Bind async responses
  to both selected ID and modal lifetime; test A -> close -> B with reversed completions.
- R012: The queue disclosure initially claims requests are processed locally by Codex/Claude.
  Only the vault and bridge are local; the client may send context to remote model providers.
- R020: Proposal review omits analysis claims/recommendation, discovery per-listing gates/scores
  and materials CV changes/citations/requirements_to_evidence while enabling Accept. Display
  every meaningful applied field or block acceptance of an unsupported payload visibly.
- R021: Queue loads only the first 50 rows and filters locally; older returned work is
  unreachable. Use server filtering and pagination and test more than one page.
- R022: Open queue cannot refresh successfully returned MCP work without navigating away.
  Provide an explicit refresh or bounded cancellable polling, preserving selected review state.
- R023: CreateWorkDialog retains a previous target on a generic reopen and permits close/reopen
  during submission without lifetime protection. Reset input per open and ignore stale replies.

## Confirmed legacy template regression requirements

Documented in templates-packets.md and T030-T033: preserve manual multi-fact claim identity,
all visible text, actual A4 DOCX sections, Unicode, safe hyperlinks, table traversal, placeholders,
and immutable historic artifact/dossier bytes. Do not weaken validators to make layouts pass.

- RT001: publishing.required_text orders summary before contacts but renderers draw contacts
  first, so a valid ATS CV with both fails the order gate. Compare semantic reading order.
- RT002: Swiss operational renderer raises LayoutError even with one short experience and
  one skill: nested KeepTogether in table cells reports a 16,777,231-point row. Render small
  and long realistic fixtures before claiming operational export support.
- RT003: sync preserves a multi-fact [A,B] block but creates another block for B because it
  records only the primary match as consumed. A pure switch changes one claim into two.
- RT004: Explicit fact deselection retains its old canvas block and then fails reference
  validation. Separate pure presentation switching from intentional evidence deselection,
  preserving unrelated manual edits while handling removed evidence visibly.
- RT005: validate_selection still requires a photo for every photo kind despite new optional
  photo policies. Gallery also clears the remembered photo asset when choosing ATS, so
  returning to a photo preset loses the selection. Test optional/no-photo and roundtrip states.
- RT006: extract_docx_text_in_order deduplicates via id(tc) without retaining lxml proxies;
  Python reuses IDs, so a synthetic 40x2 table yields only 10/80 markers. Traverse actual nodes.
- RT007: Standard labels/style defaults do not follow preset selection: German Swiss still
  renders EXPERIENCE; software/cloud PDF bytes are identical with the same canvas. Apply
  versioned presentation defaults while preserving deliberately customized headings/content.
- RT008: Swiss IT photo layouts remain centered header plus balanced columns, not promised
  semantic sidebar (gallery mismatch). Operational reading order/page breaks must match an
  explicit semantic render order and remain lossless; never bypass required-text quality.
- RT009: links.is_safe_url accepts userinfo, whitespace and https:relative and throws on
  malformed brackets. Validate authority/scheme/controls safely without raw URL-bearing errors.
- RT010: Quality accepts a PDF with Letter media box; validate A4 on every PDF page as well
  as every DOCX section, without accepting clipped/overflowed content.
- RT011: Legacy backup restore lacks preset backfill and can restore photo with software-en
  defaults. Portability owner must test old-format backups separately from database migrations.
- RT012: RENDERER_VERSION remains careeros-canvas-3.0.1 after font/byte changes. Version new
  output accurately while reading existing immutable published bytes unchanged.
- RT013: Initial test_template_quality repeats title-only required_text, its Unicode test
  uses ASCII Lodz/Zurich instead of Łódź/Zürich, table test uses a renderer without tables,
  and hyperlink test succeeds when /Annots is absent. These assertions do not test the named
  requirements. Use genuine diacritics, nested/merged tables, assert actual safe URI targets,
  all visible paragraphs/bullets/dates/contacts and real saved draft publication for nine presets.
- RT014: TemplateGallery has no feature CSS/focus isolation/Escape handling, uses untranslated
  Close text, and swallows catalog failure behind duplicated fallback metadata. Make the
  modal/gallery actually usable, accessible and truthful on API failure; test browser viewports.
- RT015: fonts.py silently falls back to Helvetica when no system Unicode font exists and
  swallows registration failures. Provide a properly licensed/inventoried local Unicode font
  or a clear unsupported-font quality failure; test with no installed optional system fonts.
- RT016: Frozen TemplatePreset still exposes shared mutable heading/style dicts, and
  operational defaults use base_font_size8.5 despite CanvasStyle minimum9. Validate every
  catalog style against the actual canvas contract and avoid mutable shared preset state.
