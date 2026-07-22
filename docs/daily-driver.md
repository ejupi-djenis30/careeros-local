# Daily-driver guide

CareerOS Local works as a complete local workspace without installing a model. The optional local
runtime can enrich matching and document analysis, but it never plans provider queries and is not
required for the workflows below. The
interface is available in English and Italian.

## Find or capture an opportunity

For provider search, create a search brief with at least one concrete target role. CareerOS first
uses only the target role and strategy you entered, plus your explicit search preferences, to build
a deterministic plan. It never turns CV text, normalized profile fields or unconfirmed model output
into provider queries. If the optional runtime is unavailable, the same search continues with this
plan rather than ending in an AI error. Set any query limit to `0` to disable that query class; an
unset limit uses the documented local default.

If you find a role in an email, referral or another website, open **Jobs**, choose **Import
listing**, and enter the role, company and source URL. The listing is stored locally and appears in
the same job review table. You can also capture a role directly from **Applications** when you do
not want it in the discovery list. Manual captures use a server-derived, per-user identifier: a
client-supplied manual platform id is ignored, retries are idempotent, and another user's identical
URL cannot share the same private listing row.

## Operate the application

Open an application card and use **Next action** for the one concrete step that should happen next.
Actions may have a due date, priority and a local calendar reminder. Complete, cancel or reopen an
action from the same panel. Every change appends a typed event, so the earlier state remains in the
timeline.

Choose **Export calendar** to download an `.ics` file for all pending dated actions in that
application. Import it into the calendar you already use. CareerOS does not contact a calendar
service or request an account connection.

## Build a verifiable application dossier

First link a published resume and clear readiness blockers. Under **Application dossier**:

1. add each concrete requirement from the role as its own row;
2. select one or more confirmed Career Vault facts for every requirement;
3. optionally add a cover letter, complete question-and-answer pairs, and checklist items within
   the limits shown in the interface;
4. publish a new dossier version.

Each publication is immutable. Downloaded ZIPs contain the selected resume files, cover letter,
answers, checklist, requirement-to-evidence matrix, one deduplicated evidence catalog, application
record and `manifest.json`. The
manifest records the byte size and SHA-256 digest of every file. CareerOS verifies the stored resume
files again before each download and refuses to export a dossier whose manifest no longer matches.
The API caps requirements, evidence links, input bytes, stored event bytes and bundle bytes before
writing anything to the timeline.

The readiness number describes only package completeness. It is not a candidate score and never
predicts whether an employer will respond, interview or hire.

## Private by default

- Search-provider calls disclose only the parameters required for that explicit search.
- Manual imports, tasks, dossier creation, exports and matching fallbacks run on the device.
- No telemetry or cloud-model fallback is built into the product.
- Dossier ZIPs and portable backups contain private career data. Store them in an encrypted
  location and remove copies you no longer need.
