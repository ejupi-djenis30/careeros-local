# Agent Working Agreement

This repository is CareerOS Local, a privacy-sensitive desktop application. These instructions apply to human and AI contributors.

## Non-negotiable product boundaries

1. Keep career data, generated documents, model weights, prompts, and inference local. Do not add cloud AI, telemetry, remote error reporting, or silent downloads.
2. Vault editing, manual records, portability, existing documents and deterministic application readiness must remain usable without a model. Any workflow presented as AI analysis, matching, tailoring, coaching or recommendation must require a ready local model and fail closed; heuristic output must never masquerade as completed AI analysis. AI output is advisory, evidence-bound, schema-validated, and never written as a confirmed fact without explicit user confirmation.
3. Accept inference endpoints only on loopback or the explicit local-container allowlist. Never weaken this validation for convenience.
4. Preserve manifest verification, path containment, archive limits, atomic writes, and the desktop vault lock.
5. Never log access tokens, desktop session tokens, prompts, resume content, source documents, model output, or personal profile fields.

## Spec-driven workflow

For material behavior changes, update the active Spec Kit artifacts in this order: constitution, specification, plan, tasks, implementation, analysis, convergence. Requirements and acceptance tests take precedence over incidental legacy structure.

Do not delete `.agents/skills`, `.specify`, or active `specs` artifacts as repository cleanup. They are development infrastructure.

## Architecture

- `frontend/src-tauri`: native lifecycle, capabilities, and packaging. Keep permissions minimal.
- `frontend/src`: React feature UI and the loopback API client.
- `backend/api`: transport only; no domain decisions.
- `backend/career`, `resumes`, `applications`, `workflows`: domain models and services.
- `backend/ai`: strict contracts, retrieval, grounding, evaluation, and local-AI capabilities.
- `backend/inference`: required-analysis readiness, managed llama.cpp lifecycle and allowlisted local development adapters.
- `backend/search`: acquisition, normalization, matching, persistence, and finalization.
- `backend/portability`: versioned backup manifest, archive, and transactional restore.

Keep new production modules focused. A compatibility facade must remain under 300 lines; do not grow a facade into an implementation.

## Change discipline

- Inspect existing behavior and tests before editing.
- Preserve unrelated user changes and never use destructive Git recovery commands.
- Use Alembic for every persistent schema change.
- Add tests for defects, security boundaries, migrations, and failure rollback.
- Use the operating system temporary directory for ephemeral test/output data. Do not create `cmd_outputs`, command dumps, ad-hoc logs, or scratch scripts in the repository.
- Avoid placeholders, silent exception handling, and claims that were not verified.

## Required validation

Run checks proportional to the change, then run all gates before release:

```text
ruff check backend tests/backend alembic/versions
mypy backend --ignore-missing-imports --no-error-summary
pytest tests/backend -q
npm test; npm run lint; npm run build
cargo fmt --check; cargo clippy --all-targets -- -D warnings; cargo test
alembic upgrade head; alembic downgrade -1; alembic upgrade head
```

Report failed or skipped checks exactly. Never describe an unexecuted check as passing.

## Git and release safety

Use a `codex/` branch for broad changes. Do not stage, commit, push, publish a release, rename the remote repository, or open a pull request unless the user requested that action. Release artifacts require checksums; signing status must be stated truthfully.
