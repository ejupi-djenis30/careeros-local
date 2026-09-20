# Data Model

## AgentWorkRequest

UUID id; owner user FK; nullable bound grant FK (ON DELETE SET NULL) and immutable historical
grant identifier retained in input provenance without a live-authority FK;
work kind discover|analyze|materials; revision >=1;
state queued|returned|accepted|rejected|canceled|expired; instruction <=4000 chars;
optional owned job/application/resume targets; preset ID/version/locale; selected fact IDs;
immutable context snapshot + canonical SHA256; profile/job/application/resume input revisions;
created/expires/updated timestamps; accepted receipt and safe error code.
Expiry is <= grant expiry, with default 24h and max 7d. Account and grant ownership must match.
Pruning a grant nulls live authority but preserves request/proposal history. No read/submit/accept
may treat a null live grant as authorized. Restore always nulls live grant and cancels pending
work; historical identifiers remain inert provenance, not references to restored live grants.
List operations return bounded metadata, not snapshot bodies.

## AgentProposal

UUID id; unique request FK (one immutable returned result per request); owner and submitting
grant IDs; idempotency key <=100 canonical printable chars; canonical payload digest;
contract version 1; client label and optional model label <=120 chars (self-reported);
validated discriminated proposal payload; created timestamp; review-required boolean.
Unique request+key semantics: same body returns original receipt, different body conflicts.
Unknown fields, unsafe markup, excess lists/text/body bytes and cross-owner evidence are invalid.
For independent retries after acceptance, return existing owned receipt without new mutations.

## Evidence and analyses

Context fact: stable fact UUID, kind, approved title/description/attributes and revision.
Contacts/private references are omitted; strings are contact-redacted before transport.
Job snapshot: owned catalog identity or proposed source identity, revision/hash, observed_at,
title/employer/location/url/text; external text is explicitly untrusted.
Gate: dimension, eligible|hold|reject, reason, fact IDs, job-source quote references and unknowns.
Scores: role/requirements/language/location/contract/freshness, integer 0..100 and explanation;
overall score uses policy fit-v1: role 25%, requirements 30%, language 15%, location 15%,
contract 10%, freshness 5%, rounded half-up to integer. All six dimensions are mandatory.
An unsupported/unknown dimension has score 0 and an explicit unknown explanation. Overall
eligibility is reject if any hard gate rejects, else hold if any gate is unknown/hold, else
eligible. Ranking score never overrides a gate; no score threshold silently implies eligibility.
Claims: plain text + nonempty evidence IDs for every career assertion. Server validates fact
membership and unsupported named entities/dates/quantities through reused grounding constraints.
Neutral letter salutations/email subject are not represented as verified career facts.

## Material proposal

Selected preset ID/version/locale; CV selected fact IDs and bounded cited overrides; cover
letter cited paragraphs; email mode short|motivational, subject/body/attachment names; bounded
question/answer claims; requirement-to-evidence list and user review notes. No path/code fields.
Owner acceptance writes existing ResumeDraft and ApplicationDossierDraft with new revisions
and generation provenance external-agent, request ID, grant ID and input/payload hashes.

## Template preset and snapshots

Immutable bundled definitions: ID, integer version, family, locale en|de, layout
ats|swiss-photo|swiss-operational, ATS/photo policy, style/section defaults and letter pairing.
IDs: software-en, cloud-platform-en, swiss-software-en, swiss-software-de,
swiss-infrastructure-en, swiss-infrastructure-de, logistics-de, retail-de, operational-de.
Compatibility template_kind remains ats|photo; photo layouts may render without a photo
according to preset policy. Old direct photo-kind behavior remains compatible.
Draft/version persist template_id, template_version and locale (additive defaults mapping legacy
ats to software-en and photo to swiss-software-en). Snapshot includes effective style/layout
metadata. Existing published file bytes never regenerate on migration.

## Application dossier extension

Existing draft/version payload gains optional letter style/template provenance and email draft.
An unpublished preparation may bind resume_draft_id instead of resume_version_id. Published
dossiers still require a verified immutable resume version. Add a migration and mutual-consistency
rules so accepting materials never publishes a CV merely to satisfy the old NOT NULL version
constraint, and never binds a new letter silently to an unrelated old resume publication.
Actual packet assets use existing digest/byte-size/storage ownership. Publication includes all
selected artifacts atomically. Staleness tracks profile/advert/application/resume/template
inputs without confusing preparation with submission.
Enhanced packet schema 3.0 has an ApplicationPacketArtifact row keyed to owned application and
published dossier identity, with contained storage path, SHA256, byte size and media type. It
stores actual immutable ZIP bytes; old schemas retain legacy reconstruction. The schema change
shares the ordered application-material migration and includes downgrade/cleanup policy tests.

## Portability and lifecycle

SourceDocument also gains source_role (profile|narrative|goals|template_reference), defaulting
legacy rows to profile. Role-aware deduplication never silently reclassifies existing content.
Preference candidates are review DTOs, not independent confirmed records; accepted preferences
use the existing profile revision/write flow. See contracts/reference-import.md.

Schema migrations include relationships, indexes, checks and supported downgrade behavior.
Backups include owned requests/proposals as historical records without active grant authority;
restored in-flight work becomes canceled and acceptance requires a new request. Grant IDs may
be retained as provenance labels without live foreign authority. Reset and erasure remove new
owned data; pending maintenance blocks all bridge reads/writes. Rollback never leaves accepted
proposals without corresponding draft updates or orphaned publication files.
