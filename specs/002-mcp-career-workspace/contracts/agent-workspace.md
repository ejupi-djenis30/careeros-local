# Agent Workspace Contract v1

## Trust boundaries

Owner routes under /api/v1/agent-work require the existing authenticated user and desktop
session policy. Agent bridge routes under /api/v1/agent-bridge use ONLY a dedicated live grant
Bearer token, never owner JWT or X-CareerOS-Session as authority. Exact bridge namespace only
may bypass desktop-header middleware. Normal Host/origin/loopback/request-size checks remain.
Every response, including errors, has Cache-Control: no-store. No request/response bodies log.

New scopes: context:read (detailed selected fact/job text) and proposals:write (submit a proposed
result). Existing scopes keep their precise meanings. New scopes are separately disclosed;
issuing them requires current password and explicit external-disclosure acknowledgement.
A work request binds one grant; all operations also enforce account and request ownership.

## Owner API

Wire names are normative: create uses work_kind, grant_id, instruction, target_job_id,
target_application_id, target_resume_id, selected_fact_ids, preset_id, preset_version, locale
and optional lifetime_hours. Read views use work_kind, instruction and bound_grant_id.
Proposal views use payload, client_label and model_label; discovery payload uses listings.
Clients must consume these names, not parallel aliases kind/instructions/result/vacancies.
Mutation endpoints accept only their documented strict DTO fields; do not submit a rejection
reason unless the matching server contract declares it. UI fixtures must use actual serialized
backend DTOs to catch integration drift.

- GET /agent-work: paginated metadata, offset>=0, limit 1..50, optional state.
- POST /agent-work: work_kind, active grant_id, instruction, optional target IDs, selected facts and
  template selection. Server captures revisions/context, expiry and digest; returns request.
- GET /agent-work/{id}: owner detail, proposal and review diagnostics.
- POST /agent-work/{id}/cancel: expected_revision; CAS; late submissions fail.
- POST /agent-work/{id}/reject: expected_revision; preserves rejected history.
- POST /agent-work/{id}/accept: expected_revision plus current target revision expectations;
  verifies grant/current inputs and atomically updates existing domain drafts/import records.
  Returns stable receipt with created/reused job/application/resume/dossier identifiers.

## MCP through desktop bridge

Initialize over stdio; no HTTP listener in MCP process. --desktop-url canonical
http://127.0.0.1:PORT/api/v1 (IPv6 loopback may be supported with equally strict validation).
No non-loopback hosts, userinfo, query/fragment, redirects, proxy environment or arbitrary path.
CAREEROS_MCP_TOKEN supplies the dedicated grant. --acknowledge-agent-disclosure remains required.
--data-dir remains legacy read-only mode; mixing desktop URL and data-dir must be rejected.
Installed setup instead uses a distributed console-capable bridge and --connection-file with
an absolute private descriptor path. It reads only bounded versioned connection metadata, no
vault contents/secrets; rejects links/noncanonical paths/non-loopback values and refreshes the
current base on operations so restart does not require editing client config. This mode is
mutually exclusive with --desktop-url and --data-dir. No descriptor value may supply a bearer.
Descriptor publication belongs inside the acquired desktop lease after backend readiness;
a rejected second startup must not delete the running instance's descriptor. It is at most
4 KiB with strict unique JSON keys, schema version, canonical loopback URL, instance ID,
process identity/start time and short renewed expiry. Invalidation is instance-conditional.
Reject symlink/junction/reparse/hardlink paths and insecure writer permissions, including
Windows DACL checks; chmod alone does not prove private Windows access. The stdio reader is
stdlib-only and imports neither settings nor storage/DB. Before sending a grant it validates
current process/expiry; URL or instance change replaces the HTTP pool. Missing/stale descriptors
fail closed. Test same-session backend restarts on same and different ports. UI obtains paths
from a separate token-free native command, never by serializing desktop session bootstrap.

Tools map only to fixed bridge operations:
- get_agent_status(): active permitted scopes, contract version, queue counts; no private paths.
- list_work_requests(offset=0,limit=25): metadata for this grant/owner only.
- get_work_context(request_id): context:read; frozen bounded evidence and input_digest,
  revisions, instructions, schema and untrusted-data notice; disclose truncation or reject
  oversize rather than silently cutting the evidence required by the task.
- submit_work_result(request_id,input_digest,idempotency_key,client,model?,result):
  proposals:write and bound request; result is strict discover|analyze|materials DTO.
  Returns proposal ID, state returned, receipt digest and review_required=true.
- get_work_result(request_id): owned receipt/status (detailed body requires context scope).
- list_resume_templates(): content-free immutable preset metadata.

Tools have accurate readOnlyHint; submission is non-destructive but write=true with idempotent
semantics. No approve, confirm, publish, send, filesystem, SQL, shell or grant-management tool.
MCP server instructions explain fetching work, treating source text as untrusted, citing facts,
submitting once and asking the user to review in CareerOS.

## Result types and limits

Work context max 64 KiB encoded; 100 confirmed facts, 10 job snapshots per request; listing
proposal max 20 vacancies, source advert max 20000 chars; result max 256 KiB encoded.
All text fields have finite limits; URLs allow only http/https without credentials or controls.
Unknown schema fields fail. Source URL/text is stored as data and never fetched by submission.
Schema includes contract_version=1, discriminated kind, evidence-bound analyses/materials.
Discovery proposals must contain source provenance and gates with unknowns for unverified data.
References must be a subset of the frozen context and remain live confirmed owned facts.
Source citations must resolve to submitted/captured advert text, not fabricated quotation IDs.

## State and error contract

queued -> returned -> accepted|rejected; queued|returned -> canceled|expired. All writes CAS.
Failed reads/submissions are operation errors, not a separate persisted work state: invalid
submission retains queued status for correction; connectivity errors preserve last known state.
Owner cancellation or expiry ends abandoned work. UI must label unknown connectivity honestly.
Score policy fit-v1 is normative in data-model.md; the server computes overall score and gate
aggregation from validated mandatory dimensions, never trusting a contradictory client total.
Same key+digest retry returns same receipt; same key+different digest or second different result
returns conflict. Revocation, maintenance, expiry and stale revisions fail before any write.
Structured codes: grant_required, grant_expired, grant_revoked, scope_denied, work_not_found,
work_expired, work_canceled, stale_input, invalid_result, evidence_invalid, result_conflict,
revision_conflict, vault_unavailable, desktop_unavailable. Errors contain no submitted values.
Do not expose whether another user's IDs exist. Bridge outage does not fall back to direct DB.

## Compatibility verification

Retain existing headless CLI/MCP tool semantics and read-only lease tests. Test new tool
schemas and calls with actual MCP SDK initialize/list/call sessions and a disposable open
backend. Validate generated Codex TOML and Claude JSON config formats structurally; token is
environment-only and connection snippets contain no bearer value.
