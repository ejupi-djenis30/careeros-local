# Windows x64 release evidence

Date: 2026-07-18  
Target: `x86_64-pc-windows-msvc`

## Build

```powershell
& .\scripts\package_desktop.ps1
```

Result: exit code `0`; Vite production build, frozen Python sidecar, optimized Tauri executable, MSI and NSIS bundles completed.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `msi/CareerOS Local_1.0.0_x64_en-US.msi` | 58,949,280 | `0b2406a75c9091a7c9fd0557e2ed82d1f84e969751acfbbe3b00e6a5be7755f4` |
| `nsis/CareerOS Local_1.0.0_x64-setup.exe` | 45,335,513 | `9c1f19f9a3dc43a863dab6b5ac3ad55c5aab48da5d7c85e30c5e057d9774a3e0` |

## Sidecar contents

```powershell
$env:EXPECTED_TARGET = "x86_64-pc-windows-msvc"
$env:GITHUB_ENV = Join-Path $env:TEMP "careeros-sidecar-env.txt"
.venv\Scripts\python.exe scripts\verify_sidecar_build.py
```

Result: exit code `0`; layout `onedir-resource`; 989 runtime files and 113,752,870 runtime bytes. The signed model catalog, catalog signature and versioned synthetic evaluation dataset were present. Generated interpreter caches and forbidden remote or legacy AI packages were absent.

## Frozen-backend lifecycle

```powershell
$env:CAREEROS_SIDECAR_BINARY = (Resolve-Path "frontend\src-tauri\binaries\careeros-backend-runtime\careeros-backend.exe").Path
.venv\Scripts\python.exe -m pytest tests\desktop\test_packaged_lifecycle.py -q -m acceptance
```

Result: exit code `0`; `1 passed in 9.83s`. A fresh temporary vault migrated, the authenticated readiness probe returned ready, and parent-process shutdown left no sidecar orphan.

## MSI/NSIS artifact export and native lifecycle

```powershell
& .\scripts\smoke_windows_installer.ps1 -IncludeNsisInstall
```

Result: exit code `0`; administrative MSI extraction and a real silent NSIS installation succeeded. The frozen backend from each installed layout created an ATS resume, exported hash-verified DOCX and PDF artifacts, and exported a validated portable backup containing its manifest, payload and resume artifacts (38,594 bytes from MSI; 38,588 bytes from NSIS). Both packages then opened a native window, retained the 495,616-byte vault, exited with code `0`, reopened offline against the same vault, preserved the vault marker, and left no sidecar orphan. Silent NSIS uninstall removed the application while preserving the user-owned vault and marker.

## Checksum inventory

```powershell
.venv\Scripts\python.exe scripts\write_artifact_checksums.py `
    --target x86_64-pc-windows-msvc `
    --output (Join-Path $env:TEMP "careeros-checksums.sha256")
Get-Content (Join-Path $env:TEMP "careeros-checksums.sha256")
```

Result:

```text
0b2406a75c9091a7c9fd0557e2ed82d1f84e969751acfbbe3b00e6a5be7755f4  msi/CareerOS Local_1.0.0_x64_en-US.msi
9c1f19f9a3dc43a863dab6b5ac3ad55c5aab48da5d7c85e30c5e057d9774a3e0  nsis/CareerOS Local_1.0.0_x64-setup.exe
```
