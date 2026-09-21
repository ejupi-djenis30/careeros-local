# Campaign API contract

All routes require the normal browser/desktop authentication and a ready vault.

## `POST /api/v1/campaigns/preview`

Multipart field `archive` (ZIP bytes). Side-effect free.

Response 200:

```json
{
  "fingerprint": "64 lowercase hex",
  "suggested_name": "Legacy application campaign",
  "suggested_profile_name": null,
  "tracker_rows": 3,
  "dossier_count": 2,
  "matched_count": 1,
  "tracker_only_count": 2,
  "dossier_only_count": 1,
  "logical_application_count": 4,
  "artifact_count": 12,
  "expanded_bytes": 12345,
  "status_counts": {"Applied": 1, "Saved": 2},
  "credential_rows_omitted": 0,
  "warnings": [],
  "sample": [
    {"source_application_id": "APP-0001", "title": "Fictional role", "company": "Example Co", "source_status": "Saved", "provenance": ["tracker"]}
  ]
}
```

Samples and warnings are bounded. No credential values are ever represented.

Errors: 400 malformed/policy failure, 413 request/archive/member limits, 422 semantic workbook
failure. Responses contain safe codes and generic messages, never archive content.

## `POST /api/v1/campaigns/import`

Multipart fields:

- `archive`: same ZIP bytes;
- `expected_fingerprint`: required preview digest;
- `name`: optional campaign display name;
- `profile_display_name`: required only when no profile exists.

Response 201 for a new import or 200 for an idempotent existing import:

```json
{
  "campaign_id": "uuid",
  "fingerprint": "64 lowercase hex",
  "created": true,
  "application_count": 4,
  "artifact_count": 12,
  "source_document_count": 3,
  "task_count": 2,
  "warning_count": 0
}
```

Errors: preview policy errors as above; 409 fingerprint mismatch or source-ID conflict; 422 missing
profile display name. The operation is atomic/idempotent.

## `GET /api/v1/campaigns`

Returns owned campaigns with aggregate counts; never returns tracker records or archive paths.

## `GET /api/v1/campaigns/{campaign_id}`

Returns owned campaign metadata, aggregate counts and bounded application projections. Supports
`query`, `stage`, `priority`, `limit` and `offset` with existing pagination conventions.

## `GET /api/v1/applications/{application_id}/campaign-context`

Returns the owned link, verbatim tracker-record object, provenance and grouped artifact metadata.
Fields are plain text only; the frontend must not interpret HTML.

## `GET /api/v1/campaigns/{campaign_id}/artifacts/{artifact_id}/download`

Streams verified owned bytes. Required headers:

- `Content-Disposition: attachment; filename="safe-name"` (RFC 5987 when needed);
- `X-Content-Type-Options: nosniff`;
- `Cache-Control: no-store`;
- exact `Content-Length` and safe stored `Content-Type`.

Digest/length/path mismatch fails closed with no partial response.
