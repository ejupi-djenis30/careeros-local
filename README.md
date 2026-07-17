# CareerOS Local

CareerOS Local is a private desktop career workspace. It keeps a detailed career profile, goals, source documents, applications, resume versions, generated files, coaching history, and AI audit metadata on the user’s device.

The application is local-first by design:

- no cloud AI provider is supported;
- no telemetry or remote analytics is included;
- model installation is optional, explicit, checksum-verified, and stored in the app data directory;
- inference is accepted only from loopback or explicitly allowlisted local container hosts;
- core profile, resume, application, backup, and editing workflows work without an AI model.

## What it does

- Builds a structured Career Vault with identity, work history, education, skills, languages, achievements, preferences, evidence provenance, and career goals.
- Generates ATS-focused or photo resumes from confirmed profile facts.
- Provides a visual resume canvas with direct editing, ordering, visibility, spacing, pagination, undo, and redo.
- Publishes immutable resume versions to PDF and DOCX after quality checks.
- Tracks opportunities and applications as a local pipeline.
- Runs a compact local model through a strict schema, evidence retrieval, validation, one repair attempt, and redacted execution audit.
- Creates manifest-verified portable backups and restores them transactionally.

## Install

Native installers are produced by the desktop release workflow for Windows, macOS, and Linux. Until a release explicitly states that packages are signed, treat them as unsigned development artifacts and verify the published SHA-256 checksum before installation.

The model is not bundled. From the home screen, review its license and size, grant consent, and install it only if AI-assisted features are wanted.

## Develop locally

Requirements: Python 3.12, Node.js 22, Rust stable, and the platform prerequisites required by Tauri 2.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
npm ci --prefix frontend
npm --prefix frontend run tauri:dev
```

Browser-mode development remains available for UI and API work:

```powershell
docker compose up --build
```

Docker uses a local Ollama container as an optional development adapter. The packaged desktop application uses the managed llama.cpp runtime.

## Verify

```powershell
.venv\Scripts\python.exe -m ruff check backend tests/backend alembic/versions
.venv\Scripts\python.exe -m pytest tests/backend -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
cargo test --manifest-path frontend/src-tauri/Cargo.toml
```

Architecture, privacy, development, security, and release details live in [docs](docs/architecture.md). The active Spec Kit feature is in [specs/001-desktop-career-agent](specs/001-desktop-career-agent/spec.md).

## License

MIT. Third-party runtimes and models retain their own licenses; the application displays the selected model license before download.
