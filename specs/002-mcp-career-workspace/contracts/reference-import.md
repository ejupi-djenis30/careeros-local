# Selected Reference Import Contract v1

The existing owner multipart POST /api/v1/career-profile/sources accepts one explicitly
selected file and optional source_role: profile (legacy default), narrative, goals, or
template_reference. SourceDocument persists source_role with an additive Alembic migration;
old rows map to profile. Do not infer authority from a filename or execute linked content.

Existing TXT/Markdown/PDF/DOCX limits, atomic asset journaling, user ownership and original
content hashes remain enforced. Text uses UTF-8 and is rendered as text, never executable
Markdown/HTML. Reject unsupported scripts/credential files and control/binary input without
logging contents. DOCX text extraction includes nested/merged tables once in document order,
with bounded traversal and extraction. Imported source bytes are copies; originals are unchanged.

Response extends SourceDocumentResponse with source_role, bounded warnings/review notes and
preference_candidates. Existing fact candidates stay compatible and unselected by default.
Profile references may produce explicitly labeled deterministic fact candidates. Narrative
and template references do not automatically produce career fact candidates: narrative is
reviewable source prose, while template text is presentation guidance and cannot establish
career truth. Goals produce only supported explicit preference candidates, never achievements
inferred from ambitions. Unrecognized prose remains visible for manual review with a clear
unsupported-field explanation; parsing is not presented as AI analysis.

A preference candidate has stable hash ID, canonical CareerPreferences field, typed value,
source locator and bounded excerpt. Support documented explicit key: value syntax for target
roles, preferred languages/locations/work modes, contract types, workload bounds, maximum
commute distance, remote-only, available-from and notice-period days. Validate through the
actual preference DTO, including cross-field constraints; do not guess unrecognized values.
Never import job-source consents, credentials, arbitrary unknown preference keys or identity
fields through this path. Limit candidates to 24 and report omitted content honestly.

Selecting candidates updates the local profile editor only after explicit acceptance; saving
the profile remains an owner action with the existing revision check. Facts stay imported/draft
until separately confirmed. Preferences are user-approved constraints, not career evidence.
The UI must make changed fields and replace/merge behavior visible; it must not silently replace
unrelated settings or persist a partial invalid preference combination. Repeated acceptance
does not duplicate facts. Duplicate bytes with the same role reuse the stored source; conflicting
role reuse is reported instead of mutating the original source classification silently.
Validate the entire proposed combination against the real preference DTO, including existing
list lengths and scalar conflicts, before mutating the editor. Different candidates for one
scalar require a visible choice; show which lists merge and which scalar values replace current
ones. Failed acceptance retains candidate selection; a later successful acceptance clears its
obsolete error. In-flight profile saves/imports cannot discard subsequent edits or file/role
selections; either prevent conflicting actions or reject stale responses by request identity.
Unknown numeric values receive omission notes just like unknown field names. Note overflow
produces a bounded explicit summary within the response's 50-note limit rather than failing
serialization or silently dropping prose. Whole-value parsing never removes a sign or truncates
a decimal to manufacture a valid integer candidate.

Tests use fictional Profile.md, Storytelling.md and Goal.md plus malicious/oversized input;
verify source hash/role, unselected defaults, no script or remote asset execution, goals not
facts, invalid preference combinations, source ownership, revision conflicts and unchanged
source files. Documentation explains the supported deterministic syntax and manual prose review.
