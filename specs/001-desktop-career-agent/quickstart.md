# Validation Quickstart: CareerOS Local Desktop Career Agent

This guide validates the implementation; it is not an installation guide for end users.

## Prerequisites

- Windows x64/arm64, macOS x64/arm64 or Linux x64/arm64 build host
- Python 3.12.13, Node 22.23.1 and current stable Rust compatible with Tauri 2
- Platform prerequisites listed by Tauri for the active operating system
- Network access only for dependency installation and the explicit model acquisition scenario

## 1. Install locked development dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes --requirement requirements-dev.lock
npm --prefix frontend ci
```

Expected: Python and npm complete without resolving unpinned direct dependencies.

## 2. Validate documentation and privacy boundaries

```powershell
.\.venv\Scripts\python.exe -m pytest tests/backend/security tests/backend/contract -q
rg -n -i "openai|anthropic|gemini|groq|deepseek|g4f" backend frontend/src desktop
```

Expected: tests pass and the search returns only explicit deny-list tests or documentation,
never a runtime client, key or fallback.

## 3. Validate Python, frontend and Rust units

```powershell
.\.venv\Scripts\python.exe -m pytest tests/backend -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
cargo test --manifest-path frontend/src-tauri/Cargo.toml
```

Expected: all suites pass; Vite produces static assets; Rust tests cover lifecycle argument and
bootstrap contracts without launching a real sidecar.

## 4. Validate migrations from empty and previous vaults

```powershell
$env:DATABASE_URL = "sqlite:///./.artifacts/empty.db"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest tests/backend/integration/test_desktop_migration.py -q
```

Expected: round-trip succeeds; the legacy fixture is backed up and upgraded; entity counts and
attachment hashes remain unchanged. `.artifacts` is disposable and must be removed after validation.

## 5. Build and smoke-test the frozen sidecar

```powershell
.\.venv\Scripts\python.exe scripts/build_backend_sidecar.py
.\.venv\Scripts\python.exe -m pytest tests/desktop -q
```

Expected: one-folder verification starts on loopback, rejects a missing/wrong session header,
reports current migrations and exits when its native parent disappears. The script prepares the
verified runtime under `frontend/src-tauri/binaries/careeros-backend-runtime/`; Tauri embeds that
directory as a private resource for the native target.

## 6. Run the desktop application in development

```powershell
npm --prefix frontend run tauri:dev
```

Expected: a native CareerOS Local window shows a readiness screen, then the local login/setup.
The process tree contains Tauri and one backend child. Closing the window stops the child.

## 7. Validate explicit managed-model setup

From the desktop model screen, choose **Install compact local model** and confirm the displayed
1,834,426,016-byte download, Apache-2.0 license and destination.

Expected:

- runtime and model downloads expose progress and can be cancelled;
- every archive/model hash matches the checked-in catalog before activation;
- the llama.cpp server binds only to a random loopback port and requires its local key;
- after completion, disconnect networking, restart the app and run the coach successfully;
- deleting the model removes managed model files without touching the career vault.

## 8. Run compact-model evaluation

```powershell
.\.venv\Scripts\python.exe -m backend.ai.evaluation validate-fixtures
.\.venv\Scripts\python.exe -m backend.ai.evaluation run --profile compact --offline
```

Expected: schema acceptance is at least 99%, accepted unsupported claims are 0%, evidence coverage
is 100%, and each task meets the thresholds in the versioned dataset manifest. The report contains
only aggregate metrics and fingerprints.

## 9. Exercise profile and resume outcomes

Create a profile with experience, quantified achievement, skills/evidence, education,
certification, language and a career goal. Generate ATS and photo drafts. On each canvas:

1. edit text and reorder blocks;
2. use undo and redo;
3. save and restore a named version;
4. export PDF and DOCX;
5. verify ATS reading order and that every claim links to a selected fact.

Expected: no unsupported claim can publish; ATS has no photo/multi-column layout; photo metadata
is absent; overflow is visible before export and never silently truncated.

## 10. Build the native installer

```powershell
npm --prefix frontend run tauri:build
```

Expected: the platform installer appears under the standard Tauri bundle directory. Install it on
a clean test account, launch without developer tools, restart offline, export a resume, upgrade over
the previous build and uninstall while retaining the vault unless deletion is explicitly selected.

## 11. Release-gate evidence

Run the tag-triggered release workflow in draft mode. Expected artifacts per platform:

- installer or application bundle;
- SHA-256 checksum file;
- Python, npm and Cargo SBOMs;
- vulnerability/license reports;
- frozen-sidecar and installed-app smoke results;
- aggregate compact-model evaluation report when the protected model runner is enabled.

No release is ready while any expected artifact or gate is absent.
