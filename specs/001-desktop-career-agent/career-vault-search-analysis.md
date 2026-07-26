# Career Vault search source — cross-artifact analysis

Date: 2026-07-26

## Decision under review

CareerOS search campaigns now treat the Career Vault as their default candidate source. An
uploaded CV remains supported for backward compatibility and explicit user choice. Each new
campaign freezes its source text and provenance so reruns use the same candidate evidence.

## Contract

| Boundary | Required behavior |
| --- | --- |
| Request | `profile_source` accepts `career_vault` or `uploaded_cv` and is optional |
| Legacy resolution | When the source is omitted, non-empty `cv_content` selects `uploaded_cv`; otherwise `career_vault` |
| Vault eligibility | A saved Vault with at least one confirmed, non-archived, non-private career fact is required |
| Snapshot content | Canonical bounded JSON uses headline, summary, relevant preferences, and eligible facts |
| Privacy | Dedicated contact, birth-date, nationality, reference, link, draft, and archived data is excluded; private prose patterns are redacted |
| Reproducibility | History stores the exact source text plus source, Vault id/revision, ordered fact ids, and SHA-256 metadata |
| Rerun | An existing history id reuses its stored snapshot and metadata without consulting or replacing it from the current Vault |
| Provider boundary | Candidate snapshot text stays local and never becomes a provider discovery query |
| Storage | Existing `cv_content` and `advanced_preferences` fields are reused; no migration is required |

## Determinism and bounds

Eligible facts are ordered by position and stable identifier. Object keys are serialized in sorted
order, list and string sizes are bounded, no more than 128 facts are considered, and the complete
UTF-8 snapshot is capped at 32,000 characters. The stored SHA-256 is calculated over the exact
serialized text.

## Failure behavior

A missing Career Vault, a Vault without an eligible confirmed fact, an explicitly selected empty
uploaded CV, or a Vault whose first eligible fact cannot fit the snapshot bound returns HTTP 422
with an actionable message. No history entry is created before these checks pass.

## Compatibility analysis

Existing callers that send CV text without `profile_source` preserve their uploaded-CV behavior.
Existing history entries continue to rerun from their stored `cv_content`; response metadata falls
back safely when older rows predate source metadata. New response fields expose the resolved source
and digest without exposing the snapshot or private profile data.
