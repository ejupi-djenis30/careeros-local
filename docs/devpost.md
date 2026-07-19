# OpenAI Build Week submission kit

This is an editing and verification brief, not copy to paste into Devpost unchanged. The
project owner should rewrite the final submission in their own voice, verify every factual
claim against the shipped build and public repository, and record the demo with their own
voice-over. Do not add adoption, performance, accuracy, or impact metrics unless they have a
reproducible source.

## Submission snapshot

- Hackathon: OpenAI Build Week
- Draft project: [CareerOS Local](https://devpost.com/software/careeros-local)
- Current observed project state: `published`; the public page is reachable without
  authentication, but the OpenAI Build Week entry is still **not submitted** because Devpost
  reports no submission timestamp.
- Live draft synced on July 19, 2026: title, tagline, structured write-up, technology stack,
  repository/portfolio/release links, and project thumbnail are populated. These fields remain
  editable and still require the owner's final voice and factual review before submission.
- Deadline observed during preparation: July 21, 2026 at 5:00 PM PT (July 22 at 02:00 CEST).
  Re-check the event page before the final upload.
- Recommended category: **Apps for Your Life**. Select one category only after the owner
  confirms it in Devpost. **Work & Productivity** is the second-best fit if the available
  category names differ.
- Repository: [ejupi-djenis30/careeros-local](https://github.com/ejupi-djenis30/careeros-local)
- License: MIT

## Positioning

### Proposed tagline

> A private, local-first career workspace that turns verified experience into resumes, job
> matches, and an application pipeline—without sending personal data to cloud AI.

Short fallback for a constrained field:

> Private, local-first career intelligence—from verified experience to applications.

Before publishing, confirm that “without sending personal data to cloud AI” still matches the
demo configuration. CareerOS Local keeps AI inference on-device; explicitly enabled job-source
providers may still use the network to retrieve public listings.

### Demo-first description draft

CareerOS Local is a Windows desktop workspace for turning scattered career history into
traceable, useful action. In the demo, a candidate imports source material into a private
career vault, reviews facts with their provenance, and uses only verified experience to build
an ATS-friendly resume. They can edit the result on a visual canvas, export it, compare local
job matches, and move an opportunity through an application pipeline.

The final scene makes the architecture tangible: the model and inference runtime are managed
locally, the canonical data store is SQLite, and the vault can be exported, restored, or
explicitly erased. The product does not depend on a cloud AI service. Network-capable job
sources remain separate, visible controls rather than a hidden inference dependency.

CareerOS Local is meant to make career AI more useful by making it inspectable. Generated
claims are grounded in evidence instead of quietly embellishing a candidate's history, while
the desktop workflow keeps sensitive documents under the candidate's control.

Edit this draft down to the strongest observed demo. Avoid describing a screen, export format,
installer, or workflow that is not present in the exact public build linked from Devpost.

## What changed during Build Week

CareerOS began before the event as the Job Hunter AI codebase, centered on job discovery and
matching. The Build Week submission must therefore be explicit that it is a substantial
extension of an existing project, not a claim that every line was created during the event.

The Build Week work transformed that base into the CareerOS Local product demonstrated here:

- a renamed and coherent local-first desktop product rather than a job-search-only identity;
- a career vault with verified facts, evidence provenance, goals, and source documents;
- resume generation, an ATS-oriented studio, visual editing, versioning, and local exports;
- job matching connected to a user-specific application pipeline;
- an on-device model/runtime flow and a Tauri desktop shell with a packaged Python sidecar;
- portable vault backup and restore, explicit erasure, privacy controls, and local AI audit
  records;
- broader Python, frontend, Rust, migration, lifecycle, security, and packaged-app validation.

Repository history from July 17–18 is the evidence source for the extension. In the final
submission, link to the public commits or comparison after they are pushed. Describe the
change qualitatively; do not use raw insertion counts as a proxy for product impact.

## Codex, GPT-5.6, and human decisions

### Verified collaboration story

Codex was used as an implementation partner across the existing Rust, Python, and React
codebase. Its work included tracing the architecture, implementing and connecting product
flows, writing migrations and tests, checking privacy and lifecycle behavior, and validating
the desktop packaging path. The build history and the majority-build Codex task should be the
evidence for these statements.

The human owner retained the product decisions: preserving local-only AI, requiring evidence
for candidate claims, choosing the desktop scope, preferring a packaged sidecar layout that
supports clean process shutdown, deciding what belonged in the demo, and accepting or
rejecting implementation trade-offs. The final category, public claims, release artifact, and
submission action are also human decisions.

### GPT-5.6 wording gate

Use the following sentence only after the `/feedback` result from the majority-build Codex task
confirms the required GPT-5.6 session and provides the session ID:

> During OpenAI Build Week, we used Codex with GPT-5.6 to turn an existing job-search codebase
> into a tested local-first desktop career workspace, while the human owner directed product,
> privacy, and release decisions.

If that session cannot be verified, do not imply a model version. Resolve the evidence gap
before submitting because the hackathon requires both Codex and GPT-5.6 usage.

## Technology stack

Product runtime:

- Tauri 2 and Rust for the desktop shell and process lifecycle
- React 19 for the desktop interface
- FastAPI and Python 3.12 for the local backend
- SQLite, SQLAlchemy, and Alembic for the canonical local vault
- llama.cpp-compatible local inference with locally managed model weights
- Pydantic contracts for validated local AI outputs

Build and verification:

- OpenAI Codex; GPT-5.6 must be confirmed by the final `/feedback` evidence
- pytest, Vitest, frontend lint/build checks, Cargo tests, Clippy, and migration checks

## Submission asset pack

- `docs/assets/careeros-local-hero.png` — generated editorial hero for the repository and
  Devpost gallery; it is conceptual artwork, not a product screenshot.
- `docs/assets/devpost-thumbnail.png` — generated square project thumbnail, designed to remain
  legible at Devpost card size.
- `docs/assets/careeros-workspace.png` — real browser-mode capture of the daily workspace using
  a fictional local profile.
- `docs/assets/careeros-vault.png` — real capture of the verified Career Vault.
- `docs/assets/careeros-resume-studio.png` — real capture of the grounded ATS resume workflow.
- `docs/assets/careeros-applications.png` — real capture of the local application pipeline.
- `docs/assets/careeros-demo.webm` and `careeros-demo-poster.jpg` — reproducible 34-second
  portfolio tour and clickable poster. This silent repository tour does **not** replace the
  narrated YouTube deliverable required for submission.

Before upload, preview each asset at Devpost's rendered size and retain the distinction between
concept art and working-product captures in captions. The screenshots contain fictional demo
data only.

## Video plan: under three minutes

Target 2:45–2:55, with a public YouTube URL and a clear voice-over. The current rules allow a
human or AI-assisted voice, but the narration must explain the project and how Codex and
GPT-5.6 were used. Show the working product; do not spend the opening minute on slides.

| Time | Picture | Voice-over focus |
| --- | --- | --- |
| 0:00–0:15 | Open CareerOS Local directly on the career vault | The problem: career data is fragmented, sensitive, and easy for generative tools to embellish. |
| 0:15–0:30 | Show the desktop shell and local status | The promise: one private workspace with on-device AI and inspectable data. |
| 0:30–0:55 | Open a source and a verified fact with provenance | Explain that resume claims come from evidence the user can inspect. |
| 0:55–1:30 | Generate a resume, edit the canvas, then show an export | Demonstrate the useful output and keep the interaction moving. |
| 1:30–1:55 | Open job matches and move one item in the application pipeline | Connect discovery to a concrete next action. |
| 1:55–2:20 | Show local model/runtime status plus backup, restore, or erasure controls | Make the local-first and ownership claims visible, including the network-source nuance. |
| 2:20–2:45 | Brief code/history view, then return to the product | State what existed before, what Build Week added, how Codex helped, and which choices remained human. |
| 2:45–2:55 | End on the product name and strongest completed workflow | Close with the candidate-control message; no unsupported metrics. |

Recording checks:

- Keep the final video below three minutes.
- Use a clean demo vault with fictional data and no personal credentials or documents.
- Make UI text legible at normal playback speed.
- Mention Codex, GPT-5.6 only after verification, and the pre-existing project honestly.
- Confirm the video is public on YouTube and accessible without authentication.

## Devpost field worksheet

Use this table while editing the draft. Field identifiers are included only to reduce final
form mistakes; Devpost labels remain authoritative.

| Field | Candidate value or action |
| --- | --- |
| Project title | `CareerOS Local` — synced to the live draft. |
| Tagline | Synced to the live draft; owner performs the final voice review. |
| Description | Structured live draft populated; owner personalizes it and removes any claim not visible in the final build. |
| Category (`27947`) | Select **Apps for Your Life** after human confirmation; choose exactly one. |
| Submitter type (`27945`) | Owner must select the truthful option. |
| Country (`27946`) | Owner must confirm the truthful country; current planning assumes Switzerland. |
| Repository URL (`27948`) | `https://github.com/ejupi-djenis30/careeros-local` after the required commits are public. |
| Test/install path (`27949`, optional) | Link the public release or exact reproducible setup path that was actually verified. |
| Codex Session ID (`27950`) | Run `/feedback` in the majority-build task and paste the returned ID; never substitute a task/thread ID. |
| Plugin/developer tool (`27951`, optional) | Describe only tools actually used and supported by evidence. |
| Built with | Use the stack above, separating the local product runtime from build-time Codex/GPT-5.6. |
| Video | Public YouTube URL, under three minutes, with voice-over. |

## Final submission checklist

Project and evidence:

- [x] Publish the completed history on the public `main` branch.
- [x] Confirm the public repository opens without authentication and still contains the MIT
  license, setup instructions, and representative source code.
- [x] Publish the source release and demo media at
  [`v1.0.0`](https://github.com/ejupi-djenis30/careeros-local/releases/tag/v1.0.0), with exact
  locked setup and verification instructions. No signed installer is claimed.
- [x] Publish the unsigned six-platform community packages at
  [`v1.0.2`](https://github.com/ejupi-djenis30/careeros-local/releases/tag/v1.0.2), with checksums,
  supply-chain evidence and GitHub build-provenance attestations.
- [x] Update the public repository description to the CareerOS Local positioning.
- [ ] Link public commits or a comparison that demonstrates the significant Build Week
  extension of the pre-existing project.
- [x] Verify the exact release build against backend, frontend, Rust, migration and packaged-app
  checks in the [`v1.0.2` release evidence](../specs/001-desktop-career-agent/release-evidence-v1.0.2.md).

Hackathon requirements:

- [ ] Owner confirms age, residency, country, and all other eligibility requirements.
- [ ] Owner confirms the final category and selects exactly one category.
- [ ] Run `/feedback` in the Codex task where the majority of the Build Week work happened;
  verify GPT-5.6 and record the real Session ID.
- [ ] Record and upload the public YouTube demo with a clear human or AI-assisted voice-over,
  under three minutes.
- [ ] Review the populated description in the owner's voice and remove every unverified claim.
- [ ] Fill all required Devpost fields and preview every external link in a signed-out browser.
- [ ] Change the Devpost project from its current published-but-unsubmitted state to `Submitted`
  before the deadline.
- [ ] Re-open the project after submission and verify Devpost displays `Submitted` and a
  submission timestamp; save a confirmation screenshot.

## Known external gaps

At the time this kit was written, the repository work alone did **not** complete these external
actions:

- the Devpost project is publicly visible with its content and assets populated, but the
  OpenAI Build Week entry still has no submission timestamp;
- no final public YouTube demo URL had been supplied;
- the required `/feedback` Codex Session ID had not been obtained;
- eligibility, country, submitter type, and final category still required owner confirmation;
- Devpost had not been verified in the `Submitted` state.

Do not mark any of these items complete based only on a local build or this document.
