# Releasing

## Preconditions

1. The specification, plan, and tasks agree; Spec Kit analysis and convergence report no unresolved critical work.
2. Python, React, Rust, migration, security, performance, and packaged lifecycle gates pass.
3. Python, npm, Cargo, and container audits have no unaccepted high/critical findings.
4. Model catalog hashes and artifact sizes were verified against authoritative upstream releases.
5. Version values agree in `pyproject.toml`, `frontend/package.json`, `frontend/src-tauri/Cargo.toml`, and `frontend/src-tauri/tauri.conf.json`.

## Local Windows package

```powershell
npm --prefix frontend run tauri:build -- --target x86_64-pc-windows-msvc
$env:CAREEROS_SIDECAR_BINARY = (Resolve-Path "frontend\src-tauri\binaries\careeros-backend-runtime\careeros-backend.exe").Path
.venv\Scripts\python.exe -m pytest tests/desktop/test_packaged_lifecycle.py -q -m acceptance
.venv\Scripts\python.exe scripts/write_artifact_checksums.py --target x86_64-pc-windows-msvc --output .artifacts/checksums-x86_64-pc-windows-msvc.sha256
```

Run the installer smoke test on a clean or disposable user profile. Verify first launch, no visible terminal, random backend port/token, model consent, offline reopen, backup/restore, clean exit, uninstall, and data retention/erasure behavior.

## CI release

Push a version tag only after approval. The desktop workflow builds the platform matrix, verifies sidecar architecture, runs packaged lifecycle tests, uploads installers, and emits SHA-256 inventories. GitHub releases remain drafts for manual review.

## Signing and evidence

Do not call an artifact signed unless platform signature verification was executed successfully. Record reproducible commands and results in the active spec’s release evidence; do not commit raw logs, local paths, secrets, SBOM output, or large build artifacts.
