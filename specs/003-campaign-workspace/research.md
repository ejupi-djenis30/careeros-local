# Research and decisions

## D1 — One user-selected ZIP, not backend directory access

**Decision**: the UI selects a ZIP. The backend receives bytes through authenticated multipart
requests for preview and commit. A repository script may build the ZIP from explicitly allowlisted
workspace paths for migration, but the product never recursively reads an arbitrary folder.

**Why**: the Tauri allowlist already supports explicit file selection; directory crawling would
broaden authority and make containment harder to audit.

## D2 — Minimal XLSX reader

**Decision**: parse the XLSX Open Packaging Convention with Python standard-library ZIP/XML
facilities. Use `xml.etree.ElementTree` for non-secret workbook/application structures and a
streaming SAX path for shared strings and the credentials worksheet so credential values are never
assembled into an XML tree or retained as cell strings. Resolve workbook relationships, shared
strings, inline strings, numeric/date styles and worksheet cells needed by the two known sheets.
Reject malformed or ambiguous structures.

**Alternatives rejected**: adding `openpyxl` to the runtime increases packaged surface for a narrow,
read-only import. CSV conversion loses workbook-sheet security semantics.

## D3 — Three normalized campaign tables plus existing assets

**Decision**: add `Campaign`, `CampaignApplication` and `CampaignArtifact`; keep all source bytes in
the existing content-addressed `CareerAsset` store. The campaign link retains the verbatim tracker
record and UI projections.

**Why**: application state stays in the existing event-sourced domain, while campaign provenance
and original fields remain immutable and queryable. Duplicate bytes are naturally deduplicated.

## D4 — Conservative status mapping

**Decision**: `Closed` maps to `archived`, never `rejected`; original status/outcome remain stored.
When a closed record contains a real application date, import an applied event before archived.

**Why**: “closed” does not prove rejection, withdrawal or employer action.

## D5 — Historical materials are evidence, not native drafts

**Decision**: packet PDFs, DOCX/HTML/MD/email/scripts are inert campaign artifacts. Root reference
documents that match current source roles are additionally registered as reviewable source
documents. No historical CV is promoted to a verified resume version automatically.

**Why**: native resume versions require grounded facts and publication invariants absent from
legacy files.

## D6 — Idempotence by canonical fingerprint

**Decision**: unique `(user_id, source_fingerprint)` on Campaign. Preview and commit both compute the
fingerprint from sorted canonical member records. Commit compares the user-supplied expected value
and returns the existing campaign on a duplicate.

## D7 — Inert downloads

**Decision**: all downloads require ownership checks and set `Content-Disposition: attachment`,
`X-Content-Type-Options: nosniff`, no-store caching and the stored safe media type. No imported HTML
or script is inserted into the DOM.

## D8 — Existing profile bootstrap

**Decision**: import uses the current candidate profile. If none exists, the preview may offer a
locally parsed display-name suggestion, but commit requires an explicit display name and creates
only the minimal profile. Source facts remain pending review.

## D9 — Real data validation without private fixtures

**Decision**: all committed automated fixtures are fictional and tiny. A local validation command
accepts a user-selected archive and emits only aggregate counts/digests. Its expected real-campaign
counts are documented in the feature validation file; it never writes source content to logs.

## D10 — Development agent boundary

**Decision**: Codex authors the feature artifacts and acceptance harness, then drives one
Antigravity CLI conversation with `gemini-3.8-flash-high`, accept-edits mode, the repository as cwd
and no permission bypass. Codex reviews the diff and runs gates; fixes are sent back through the
same CLI conversation. The implementation agent must honor `AGENTS.md` and these artifacts.

## D11 — Dossier directory reconciliation

**Decision**: a packet directory is matched by its complete source application ID first. If the
directory name carries a descriptive suffix, match the longest tracker ID followed by `_` and keep
the complete directory name only as provenance. Reject an archive when two directories resolve to
the same source ID. If no tracker ID matches, retain the directory name unchanged as a dossier-only
source ID.

**Why**: 19 audited packet directories use `<source-id>_<descriptive-slug>` while the other packet
directories use the bare source ID. Treating the entire directory name as the ID incorrectly turns
those 19 matches into duplicate logical applications.

## D12 — Persist a credentials-free tracker derivative

**Decision**: never publish the original `ApplicationTracker.xlsx` bytes to `CareerAsset`. Build a
deterministic, valid XLSX containing only the parsed `Applications` header and rows, using inline
strings so no original shared-string table survives. Store that derivative as the campaign's
`tracker` artifact and retain only the original member digest on `Campaign`.

**Why**: deleting only the visible credentials worksheet is insufficient because credential values
may remain in `sharedStrings.xml`. A minimal reconstructed workbook makes the exclusion auditable,
keeps the logical artifact count stable and lets the user download their non-secret tracker data.

## D13 — Deterministic historical timeline and task planning

**Decision**: build an immutable, side-effect-free import plan before opening a write transaction.
The planner accepts one aware UTC `imported_at` instant and emits the exact stage path in the data
model. Date-only source values are represented at 12:00 UTC. Event instants are capped at
`imported_at` and made strictly increasing by moving earlier events backward by one microsecond
when source dates are missing, equal or out of order. The source dates themselves remain verbatim
in campaign metadata.

Only a non-closed tracker row with a non-blank `Next Action` receives a pending task. Its title is
the trimmed source value, its due instant is `Follow-up Date` at 12:00 UTC, and its priority maps
`Urgent→urgent`, `High→high`, `Medium→normal`, `Low→low`, with unknown values falling back to
`normal`. Dossier-only records and closed rows receive no imported task. Task identifiers are
derived deterministically from the campaign fingerprint and source application ID.

**Why**: the plan can be exhaustively tested without writes, retries cannot change the intended
timeline, historical source dates remain useful, and import never invents rejection or active work.
