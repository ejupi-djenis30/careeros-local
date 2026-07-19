# Releasing

## Preconditions

1. The specification, plan, and tasks agree; Spec Kit analysis and convergence report no unresolved critical work.
2. Python, React, Rust, migration, security, performance, and packaged lifecycle gates pass.
3. Python, npm, Cargo, and container audits have no unaccepted high/critical findings.
4. Model catalog hashes and artifact sizes were verified against authoritative upstream releases.
5. Version values agree in `pyproject.toml`, `frontend/package.json`, `frontend/src-tauri/Cargo.toml`, and `frontend/src-tauri/tauri.conf.json`.

Run the same metadata gate used by CI before creating a tag:

```powershell
.venv\Scripts\python.exe scripts\check_release_versions.py
```

## Local Windows package

```powershell
npm --prefix frontend run tauri:build -- --target x86_64-pc-windows-msvc
$env:CAREEROS_SIDECAR_BINARY = (Resolve-Path "frontend\src-tauri\binaries\careeros-backend-runtime\careeros-backend.exe").Path
.venv\Scripts\python.exe -m pytest tests/desktop/test_packaged_lifecycle.py -q -m acceptance
.venv\Scripts\python.exe scripts/write_artifact_checksums.py --target x86_64-pc-windows-msvc --output .artifacts/checksums-x86_64-pc-windows-msvc.sha256
```

Run the installer smoke test on a clean or disposable user profile. Verify first launch, no visible terminal, random backend port/token, model consent, offline reopen, backup/restore, clean exit, uninstall, and data retention/erasure behavior.

## CI release

Run `Desktop packages` manually from `main` before creating a version tag. A manual run builds
the full native matrix and retains smoke-tested packages as workflow artifacts without changing
any GitHub release.

After that rehearsal passes, push a matching version tag. The tag workflow freezes the backend,
verifies every sidecar architecture, exercises packaged lifecycle and installer behavior, writes
SHA-256 inventories, creates GitHub build-provenance attestations, and uploads the packages only
after those gates pass. A final least-privilege job creates a draft, attaches the verified assets
and supply-chain evidence, then publishes the release. A failed native job cannot publish or
modify a release.

## Signing and evidence

Do not call an artifact signed unless platform signature verification was executed successfully.
Until signing is configured, release notes must label community packages as unsigned. Verify
GitHub provenance after downloading a package:

```powershell
gh attestation verify .\CareerOS-Local-installer.exe -R ejupi-djenis30/careeros-local
```

Record reproducible commands and results in the active spec’s release evidence; do not commit raw
logs, local paths, secrets, SBOM output, or large build artifacts.
