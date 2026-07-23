# Daily-driver guide

CareerOS Local keeps ownership separate from analysis. You can maintain the Career Vault, edit and
publish documents, capture applications manually, run readiness checks, and export or restore data
without a model. Opportunity matching and coaching require a ready
local model. The app checks the runtime, selected model, and structured-output contract before it
opens those workflows. The interface is available in English and Italian.

## Prepare local analysis

The desktop app manages its default llama.cpp-compatible runtime and verifies the selected model
before analysis begins. Open an analysis workflow, review the model license, install the listed
model, and wait for all four readiness checks to pass: local endpoint, reachable runtime, available
model, and valid structured output. The probe contains no Career Vault data.

If readiness fails, use **Check again** after the runtime or model is restored. CareerOS shows a
stable diagnostic code and keeps analysis locked; it does not invent a heuristic result. When
Windows application-control policy blocks the bundled runtime, CareerOS can use an official Ollama
installation as a production local fallback through the same readiness and schema checks. Install
it from the [official Windows download](https://ollama.com/download/windows), start the local
service, and install the model selected in CareerOS. CareerOS does not install Ollama for you.
Keep Ollama cloud features disabled and never point `LOCAL_INFERENCE_URL` at a remote host.

## Find or capture an opportunity

For provider search, create a search brief with at least one concrete target role. CareerOS first
uses only the target role and strategy you entered, plus your explicit search preferences, to build
a deterministic plan. It never turns CV text, normalized profile fields or unconfirmed model output
into provider queries. A ready local model is still required because every retained opportunity
must pass validated matching analysis. If the runtime is unavailable, search stops before provider
work begins and no heuristic match is stored. Set any query limit to `0` to disable that query
class; an unset limit uses the documented local default.

If you find a role in an email, referral or another website, open **Jobs**, choose **Import
listing**, and enter the role, company and source URL. The listing is stored locally and appears in
the same job review table. You can also capture a role directly from **Applications** when you do
not want it in the discovery list. Manual captures use a server-derived, per-user identifier: a
client-supplied manual platform id is ignored, retries are idempotent, and another user's identical
URL cannot share the same private listing row.

## Operate the application

Start with **Next actions** at the top of Applications. It brings together the current projected
action from every active application and orders overdue work first, followed by work due today,
the next seven days, undated tasks and applications that still need an action. The local-day
boundary is the next local midnight calculated by the browser calendar, so daylight-saving
transitions do not inherit a stale fixed offset. The queue refreshes at the next returned deadline
or local midnight, and whenever the window regains focus or becomes visible. Actions beyond seven
days and rows beyond the compact view are counted explicitly; the full board always remains below
it.

This agenda is a deterministic local read model. It reads only the authenticated user's scalar
application projections, does not inspect task-event bodies, and does not need the local model. If
the agenda cannot load, application cards and manual task editing remain available. Counts and
rows come from one SQL-statement snapshot, so a concurrent application update cannot mix an old
total with a new row list.

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
- Manual imports, tasks, dossier creation, exports and local-model analysis run on the device.
- No telemetry or cloud-model fallback is built into the product.
- Dossier ZIPs and portable backups contain private career data. Store them in an encrypted
  location and remove copies you no longer need.
