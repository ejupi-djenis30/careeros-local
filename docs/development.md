# Development

## Toolchain

- Python 3.12
- Node.js 24 LTS and npm
- Rust stable compatible with the `rust-version` in `frontend/src-tauri/Cargo.toml`
- Tauri platform prerequisites

Install exactly the locked dependencies:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
npm ci --prefix frontend
```

Desktop sidecar packaging uses the separate, hash-locked `requirements-tooling.lock`. Regenerate
locks only from their reviewed input files:

```powershell
.venv\Scripts\python.exe -m piptools compile --generate-hashes --output-file requirements.lock requirements.txt
.venv\Scripts\python.exe -m piptools compile --generate-hashes --allow-unsafe --output-file requirements-tooling.lock requirements-tooling.txt
```

## Run

Native development:

```powershell
npm --prefix frontend run tauri:dev
```

Browser/container development:

```powershell
docker compose up --build
```

Manual backend and frontend:

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
npm --prefix frontend run dev
```

## Database changes

Import all mapped models through `backend/model_registry.py`. Create an Alembic revision, review it manually, and validate:

```powershell
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\alembic.exe downgrade -1
.venv\Scripts\alembic.exe upgrade head
```

Never replace a migration with a runtime `create_all` workaround.

## Tests and quality

```powershell
.venv\Scripts\python.exe -m ruff check backend tests/backend alembic/versions scripts/check_release_versions.py scripts/seed_demo.py scripts/render_demo_assets.py
.venv\Scripts\python.exe -m mypy backend scripts/check_release_versions.py scripts/seed_demo.py scripts/render_demo_assets.py --ignore-missing-imports --no-error-summary
.venv\Scripts\python.exe -m pytest tests/backend -q --cov=backend --cov-branch --cov-fail-under=80
npm --prefix frontend run test:coverage
npm --prefix frontend run lint
npm --prefix frontend run build
cargo fmt --manifest-path frontend/src-tauri/Cargo.toml --check
cargo clippy --manifest-path frontend/src-tauri/Cargo.toml --locked --all-targets -- -D warnings
cargo test --manifest-path frontend/src-tauri/Cargo.toml --locked
```

Tests deny public network access unless explicitly marked `live`. Use `TemporaryDirectory` for generated test data and never persist command output in the repository.

The portfolio media is also reproducible and uses only a disposable loopback vault. See the
[demo recording guide](demo.md) or run `npm --prefix frontend run demo:record`.

## Spec Kit

Material work belongs in a numbered `specs` feature with specification, plan, tasks, acceptance criteria, and convergence. Keep task checkboxes truthful and run cross-artifact analysis before release.
