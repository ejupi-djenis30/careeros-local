# Job providers

Open **Providers** in the sidebar, or **Manage providers** under Career Vault preferences.
This workspace stores job-source configuration in the authenticated account's local vault.
Configuration, import, deletion and backup do not require a model. Matching and coaching retain
their separate local-model readiness checks.

A new vault has no installed network providers. Only the local job archive is available until
you configure or explicitly import a source. Opening this page, validating a declaration and
importing a pack do not fetch job listings.

## Configure a source

Choose **New provider**, enter a display name and a stable key, then select **JSON API** or
**HTML**. Set a public HTTPS origin and a separate request path. Map at least the provider's
job `id` and `title`, review the remaining fields and choose **Save provider**. Leave
**Enable network access** unchecked until you want this source to participate in searches.

The saved configuration receives an account-owned UUID `id` and starts at revision 1. Its
`key` identifies the source in searches and must be unique within that account: 2–64 lowercase
letters, digits, underscores or hyphens, beginning with a letter. `local_db`, `job_room`,
`swissdevjobs` and `adecco` are reserved for the local archive and reviewed native adapters.

Use **Edit** for declarative sources. Save, enable/disable and delete operations compare the
revision you reviewed with the current revision. If another window changes the source, CareerOS
reports a conflict instead of overwriting it. Reload the page, inspect the current source and
apply the intended change again. Deleting a configuration does not delete stored job listings.

### JSON and HTML mapping

JSON sources use dotted object paths, such as `jobs` for the items array, `total` for an optional
result count and `company.name` for one mapped field. They do not execute JSONPath expressions.
HTML sources use a bounded selector subset: tags, classes, IDs, attribute filters and descendants.
For example, `article.job-card` can select each item, `.title` its title and `a` with attribute
`href` its URL. HTML is parsed as data; CareerOS does not execute page scripts or imported code.

The canonical mapped fields are:

| Field | Meaning |
| --- | --- |
| `id`, `title` | Required source identifier and job title |
| `company`, `location`, `description` | Employer, location text and description |
| `url` | Original listing URL |
| `application_url`, `application_email` | Advertised application channels |
| `posted_at` | Publication date in an ISO date/time representation |
| `workload_min`, `workload_max`, `country_code` | Workload percentages and country code |

Advanced settings control GET/POST, query parameters, an optional POST JSON body, headers,
pagination, timeouts, response size, throttling and bounded retries. Supported placeholders are
`{query}`, `{location}`, `{language}`, `{page}`, `{page_one_based}`, `{page_size}`, `{offset}`,
`{workload_min}` and `{workload_max}`. `{page}` starts at zero. A declaration cannot import a
Python module, shell command or executable scraper.

Declarative destinations must use public HTTPS on port 443, without URL credentials, query or
fragment in the origin. Paths stay on that origin. Each request validates DNS and connects to a
validated public address while preserving TLS hostname verification. Redirects and ambient proxy
settings are disabled. Private, loopback and local-network destinations are rejected. This job-source
policy is separate from the loopback-only local inference configuration.

## Network consent and testing

**Enable network access** is saved consent for future searches. Enabling a provider does not
start a search; disabling it removes it from subsequent provider acquisition. Search queries
still come from explicit search intent and preferences, not undisclosed career-document uploads.

**Test** is separate, one-shot consent. The confirmation names the provider and the fixed test
query, **software engineer**, with an empty location and language `en`. Cancel sends no test
request. Confirm runs a bounded first-page diagnostic and displays at most five mapped jobs;
it neither saves a search result nor enables the source. A disabled source can be tested this way.
Offline mode rejects the test without acquiring listings. Normal request/response and retry
limits still apply.

## Import documents and the bundled pack

Leave **Enable imported providers immediately** unchecked to inspect imported sources first.
Selecting it explicitly grants those imported sources network access for later searches.
Import itself does not acquire listings. Imports are atomic: an invalid entry, duplicate key or
conflict rejects the whole document instead of installing a partial pack.

Choose a JSON file of at most 256 KiB. A single document has `kind: "provider"`,
`format_version: 1` and one `provider` entry. A pack uses `kind: "provider_pack"`,
`format_version: 1`, `id`, semantic `version`, `name`, optional `description` and a `providers`
array of 1–20 entries. Each declarative entry must contain `enabled: false` and empty `headers`.
Add any credentials locally after import; shareable files cannot contain configured headers.

This minimal JSON document uses a reserved example domain as documentation data. It is not a live
provider or a recommendation. Replace the origin and mappings with an authorized public source
before deliberately testing it.

```json
{
  "kind": "provider",
  "format_version": 1,
  "provider": {
    "kind": "declarative",
    "configuration": {
      "key": "example_jobs",
      "display_name": "Example jobs",
      "adapter_kind": "json",
      "enabled": false,
      "request": {
        "base_url": "https://jobs.example.test",
        "path_template": "/api/jobs",
        "method": "GET",
        "query_params": { "q": "{query}", "page": "{page}" },
        "headers": {}
      },
      "extraction": {
        "items_path": "jobs",
        "fields": {
          "id": { "source": "id" },
          "title": { "source": "title" }
        }
      }
    }
  }
}
```

The bundled **Swiss job providers** pack has canonical ID `careeros.switzerland.core`, version
`1.1.0`. It is source-controlled application data, not an automatic download or installation.
Choose **Import pack** to install its eleven entries:

| Provider key | Adapter |
| --- | --- |
| `job_room`, `swissdevjobs`, `adecco` | Reviewed native adapters |
| `canton_bern`, `canton_solothurn`, `canton_lucerne` | Declarative HTML |
| `fmh_doctor_jobs`, `vmi_npo_jobs`, `swissolar_jobs` | Declarative HTML |
| `kampajobs`, `jobs_for_change` | Declarative HTML |

Native entries must use exactly `job_room`, `swissdevjobs` or `adecco` as both `adapter_id`
and `key`; arbitrary module paths and aliases are rejected. Native sources can be enabled,
disabled, tested or deleted, but their built-in implementation cannot be edited in the form.
Pack import creates owned installations; it does not silently update existing configurations.

## Credentials and origin changes

Every configured header value is confidential, including custom header names. It stays in the
local vault; reads return `••••••••`, not the original value. Keep credentials in headers, never
in query parameters or JSON bodies: those configuration fields are not secret storage.

On a same-origin edit, the form preserves masked header values. When changing the origin of a
source with stored headers, either replace **Static headers (JSON)** with `{}` or explicitly
re-enter the headers appropriate to the new origin. A masked value, preservation marker or
omitted headers cannot transfer the old credentials. The API returns `secret_origin_changed`
and leaves the saved source unchanged. Hostname case and explicit port 443 normalize to the
same origin; a different hostname does not.

## Backup, restore and erasure

Portable archive format 9 includes provider configurations and supports a vault containing only
providers, without inventing a career profile or facts. Configured headers are excluded. After
restoring, **every provider is disabled**, including native sources and sources that had no
credentials. Review the destination and mappings, re-enter required headers locally, then
explicitly enable the sources you want. Backups retain source and pack identifiers, not network
permission or active agent authority.

Restore requires an empty destination vault and does not overwrite another account's records.
Older formats 1–8 remain supported with an empty provider inventory. Complete vault reset and
erasure include the account's provider configuration; deleting one provider remains a separate
configuration action. Portable ZIP checksums verify integrity, not authorship or encryption.

## Local API contract and agent boundary

The desktop UI uses authenticated, account-scoped `/api/v1/job-providers` endpoints. The `id` in
the following paths is the saved configuration UUID, not its stable `key` or a pack ID.

| Operation | Relative path and revision contract |
| --- | --- |
| List / create | `GET` / `POST /job-providers` |
| Validate without acquisition | `POST /job-providers/validate` |
| Read / update | `GET` / `PUT /job-providers/{id}`; update includes `expected_revision` |
| Saved activation | `PATCH /job-providers/{id}/state` with `enabled`, `expected_revision` |
| Delete | `DELETE /job-providers/{id}?expected_revision=…` |
| One-shot diagnostic | `POST /job-providers/{id}/test` with literal `allow_network: true` |
| Import a document | `POST /job-providers/import` with `{ "document": …, "activate": false }` |
| Import the bundled pack | `POST /job-providers/packs/careeros.switzerland.core/import` with `activate` |

Missing or false test consent is rejected. A stale revision returns a conflict; another account's
UUID is not readable or writable. Provider setup introduces no MCP tool, scope or grant authority.
External agents retain the current bounded proposal workflow: they cannot manage these
configurations through MCP, confirm facts, accept proposals, publish materials or send applications.
