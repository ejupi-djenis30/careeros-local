# CV-first first result — convergence

## Requirement convergence

| Requirement | Evidence |
| --- | --- |
| Existing-CV and manual choices | Home setup renders separate routes and labels in English and Italian. |
| Profile before source | `CareerProfilePage` awaits its ordinary revisioned save before `SourceImporter` releases the file to the local upload service. |
| No upload after write failure | Focused tests assert zero source calls after a rejected initial profile write. |
| Retry preserves selection | Source importer tests cover preparation and upload failure with the original filename and enabled retry control still present. |
| No redundant revision | An existing-profile test proves the source upload runs without a profile save. |
| Human confirmation | Accepted candidates retain `imported`; copy states this explicitly and the review action focuses the facts heading. |
| Local-only behavior | The implementation imports only Career and source services and adds no inference, analytics or remote client. |

## Validation evidence

Executed on Windows with Node.js 24.18.0 x64:

| Gate | Result |
| --- | --- |
| Focused Career Profile, Source Importer and Home tests | Passed: 3 files, 22 tests |
| Full frontend test suite | Passed: 67 files, 362 tests |
| Frontend license-policy tests | Passed: 3 tests |
| `npm run lint --prefix frontend` | Passed |
| `npm run build --prefix frontend` | Passed; Vite emitted the existing informational warning for a chunk above 500 kB |
| `git diff --check` | Passed |

The focused suite includes an axe accessibility scan after the CV-first candidate review is
rendered. Python, Rust and Alembic gates were not run for this slice because it changes no Python,
Rust, database schema, migration or packaged lifecycle behavior. No release artifact was built or
published.

## Decision

The first-use blocker is resolved without weakening the source-import precondition or automatically
trusting extracted text. The CV-first path is ready for pull-request review. Release publication
remains a separate, fully gated decision.
