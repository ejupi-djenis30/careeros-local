# Template and Packet Contract v1

## Catalog and selection

GET /api/v1/resumes/templates returns immutable preset definitions: id/version/name/family/
locale/layout/ATS/photo policy/page budget/letter pairing plus safe declarative preview style.
Owner-authenticated draft create/update accepts template_id, template_version and locale;
legacy template_kind remains supported. Unknown IDs/versions fail; mismatched legacy kinds are
normalized only when explicit preset selection makes the intended layout unambiguous.
A content-preserving switch applies presentation defaults, never replaces selected facts,
overrides, canvas text or career-truth references. Preview and export use the same effective
preset and template version. Legacy snapshots without metadata map deterministically.

Nine presets cover seven families; ATS and Swiss photo CVs default <=2 A4 pages, operational
presets <=1. Letters default <=1. Over-budget output is a visible publication blocker with
actionable editing guidance. ATS omits photos and preserves single-column reading order.
All presets include EN or DE section labels matching declared locale; language selection does
not silently translate approved content. AI translation requires a separate reviewed request.

## Materials and packet

Use existing application dossier API/versions; owner edit/accept/publish remains explicit.
Cover letter: bounded plain structured paragraphs with career fact citations; heading/date/
recipient/subject local fields; paired layout; local PDF/DOCX.
Email: mode short|motivational, recipient optional until export selection, subject, plain body,
selected attachment names. Generate an offline email draft and checklist. Never open SMTP or
send. Validate header control characters and attachment names; no arbitrary attachment paths.
Answers: question text/ID, supported claim text and evidence; empty or unsupported answers are
review blockers. Packet manifest records only actual artifacts with existing hashes/lengths.
Source advert and fit/evidence notes use owner snapshots and self-reported agent provenance.
Do not include live token, grant secret, private absolute path or unselected personal references.

### Draft bindings and enhanced packet compatibility

ApplicationDossierDraft accepts exactly one owned resume_draft_id or resume_version_id.
An unpublished draft binding records the resume draft revision as well as application/profile/
advert revisions. Existing version-bound requests stay compatible. Publishing requires an
explicitly selected verified ResumeVersion from that same draft with current approved inputs;
accepting a proposal never publishes it implicitly or silently uses an unrelated older version.

Preserve existing cover_letter, answers, checklist and requirement_matrix fields. Extend draft
and publish DTOs with optional typed letter_options (preset/version/locale, recipient, subject,
date, selected pdf/docx formats), email_draft (mode, recipient, subject, body, attachment_names)
and generation_provenance/evidence metadata. Field names must be shared by serialized backend
DTOs, frontend autosave and the later agent material adapter. Incomplete manual drafts can save;
publication performs final required text, placeholders, stale revision, A4/page/text and selected
attachment checks. No external API or email send operation is added.

Legacy packet schemas 1.0/2.0 retain their byte-stable reconstruction path. Enhanced packets
use schema 3.0 and persist their actual ZIP bytes atomically with digest/size and owned dossier
identity, using a new migrated ApplicationPacketArtifact record. Do not reconstruct new letter
PDF/DOCX with a future renderer and pretend the result is the original publication. A failed
file/metadata write rolls back all publication state and leaves no orphan bytes. New artifacts
participate in portability/restore/reset and existing maximum archive/member bounds. Old packet
content is never extended by default during download. The manifest lists precisely the actual
selected files, including source advert, evidence, matched letter and offline email/checklist.

Expose a focused flush-only dossier draft mutation seam for outer agent-acceptance transactions.
It performs ownership, binding and CAS validation, but neither commits nor publishes. Existing
owner routes wrap it with their normal commit/rollback behavior. Characterize legacy methods
before extracting dossier orchestration from ApplicationService; preserve public import paths.
The seam neither commits nor rolls back its caller's transaction. Use database revision CAS,
including independent-session tests; loaded-object comparisons alone do not prevent lost edits.
Publication compares the complete saved publishable payload, including letter/email options and
provenance. Its readiness and fingerprints describe the selected verified CV, not a previously
linked version. Profile and CV-draft revision counters are distinct and cannot substitute for
proof that a published version represents the approved draft content.

An uncertain commit outcome requires reconciliation before artifact deletion. Successful commit
followed by journal-cleanup failure preserves the committed packet. Journals remain until cleanup
succeeds, are recovered under the vault lock and never authorize deleting another publication's
bytes. Downloads dispatch on event schema: missing schema 3 artifact metadata/bytes is a clear
integrity failure, never permission to rebuild it as schema 1/2. Verify artifact, event and
manifest identity together. Letter rendering escapes every untrusted text fragment and inserts
only safe generated hyperlink markup; supplied resource tags cannot read files or access networks.

### Owner artifact retrieval

`GET /api/v1/applications/{application_id}/dossiers/{dossier_id}/artifacts/{filename}`
downloads one reviewed schema 3 artifact for the authenticated owner. `filename` is an enum,
not a storage path: `resume.pdf`, `resume.docx`, `cover_letter.pdf`, `cover_letter.docx`,
`email_draft.eml`, or `email_checklist.txt`. The service opens the already verified immutable
packet bundle, requires the requested member to be declared by that packet's manifest, and
revalidates its digest, size, application and dossier identity before returning bytes. It never
extracts a member to persistent storage and never falls back to rebuilding schema 1/2 packets.
Unknown names, path syntax, missing members, altered metadata or altered bytes fail closed with
content-free errors. Responses use the manifest-bound media type, a safe attachment filename,
and `Cache-Control: no-store`; cross-owner requests reveal no artifact data. The packet ZIP
download remains available unchanged.

## Quality and portability

Preserve existing required-text/sections/image sanitation/hash/atomic storage checks.
Validate PDF text and page dimensions/count, DOCX text including tables, links/diacritics and
absence of unresolved placeholders/raw instructions. Verify every selected attachment exists.
Every visible summary, paragraph, bullet, date and contact field must survive export, not only
entry titles. Each DOCX section must explicitly use A4. Embedded Unicode-capable local fonts
must preserve supported diacritics in PDF extraction. Links are real safe URI hyperlinks in
PDF and DOCX. DOCX text traversal includes nested tables in document order without duplicate
merged cells. A pure template change must preserve manual block IDs and multi-fact evidence,
hidden sections and ordering; it must not implicitly resynchronize away manual provenance.
Generated HTML previews contain no scripts/remote fetches; render text escaped via React/local
renderers. Arbitrary HTML/CSS template import is unsupported.
Old published bytes stay immutable. New snapshots and packet payloads roundtrip through backup
with relationships validated and no resurrection of agent grant authority.

## Reference import

Supported initial sources are explicitly selected UTF-8 .md/.txt and existing supported
document imports. Input role profile|narrative|goals is explicit; parsed candidates require
owner review before confirmed facts/preferences. Processing is deterministic extraction only
unless submitted to an authorized agent workflow; never claim it is completed AI analysis.
Bound bytes and file counts, reject symlinks/archive paths/executables, preserve source hashes
and original files. The product does not recursively ingest the Career folder.
