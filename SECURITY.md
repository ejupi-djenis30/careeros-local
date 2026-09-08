# Security Policy

## Supported versions

Security fixes target the latest release and the current `main` branch. Pre-release builds and unsigned local artifacts are provided without an authenticity guarantee beyond their published SHA-256 checksum.

## Report a vulnerability

Use GitHub private vulnerability reporting for `ejupi-djenis30/careeros-local`. Do not open a public issue containing personal data, tokens, archive contents, exploit details, or unredacted logs. Include the affected version, platform, reproduction steps, and impact. Acknowledgement is targeted within seven days.

## Security boundaries

- The Tauri shell starts a randomly authenticated backend on IPv4 loopback and terminates it with the desktop lifecycle.
- The API rejects non-loopback desktop hosts and remote inference endpoints.
- The packaged inference runtime uses a per-launch API key and a verified catalog, archive size, exact byte count, SHA-256 digest, safe extraction, and executable marker.
- Portable archives enforce format compatibility, member/count/size limits, path containment, hashes, relational preflight, exclusive vault locking, and rollback.
- Resume and source files are stored by contained relative paths and written atomically.
- Logs and AI audits contain metadata and fingerprints, not prompt or output bodies.

## Local risk model

CareerOS Local does not protect data from a fully compromised operating-system account, malware with user-level file access, screenshots, or malicious local accessibility tools. Use OS disk encryption, a protected user account, and trusted backups. A local model can still produce inaccurate advice; users must verify consequential decisions.

## Dependency and release controls

CI runs hash-locked Python installs, npm lockfile installs, Rust lockfile builds, audits, SBOM generation, secret/misconfiguration scanning, migration round-trips, tests, and package checksums. A vulnerability exception must be documented with scope, rationale, expiry, and compensating control.

## Patched local Ollama runtime (2026-09-08)

Fresh Trivy 0.72.0 scans found **42 HIGH and 1 CRITICAL** findings compiled into `usr/bin/ollama`
in both the formerly pinned 0.32.0 image and the reviewed upstream 0.33.3 image. The critical
finding was CVE-2026-56854 in `golang.org/x/crypto` v0.43.0. Updating Ubuntu packages cannot replace
a Go module embedded in that executable, so the expired exception inventory was removed instead
of being extended.

Compose now builds `careeros-local-ollama:0.33.3-careeros.1` from these immutable inputs:

| Input | Reviewed identity |
| --- | --- |
| Ollama source | commit `b79067b0db7417f20108363bc22adb97f35c966a`, the v0.33.3 release |
| Source archive | SHA-256 `8f1c4cfe1c687918e00bf9ab6f9966ebd4d727d3d64ccb109b2561afcd347b07` |
| Go builder | `golang:1.27.1-bookworm` at `sha256:648f440f42a0958804efb24df176f806f9d353b41f1c0627f666428e40310f6b` |
| Native runtime base | `ollama/ollama:0.33.3` at `sha256:32931b46719f673c05fdbaa81ccb26da18ea4a1c57590a754874ab28ba269eb2` |

The build upgrades the affected module graph to `jsonparser` 1.1.2, `x/crypto` 0.55.0,
`x/image` 0.45.0, `x/mod` 0.40.0, `x/net` 0.57.0, `x/sync` 0.22.0, `x/sys` 0.47.0,
`x/term` 0.45.0 and `x/text` 0.41.0, then verifies the resolved versions before compiling. It
replaces only the upstream Go executable and regenerated `GO_LICENSE`; the reviewed 0.33.3
CPU/GPU runtime payload, entry point and local service contract remain unchanged. The image stores
`go version -m` output, source identity and executable checksum in
`/usr/share/doc/careeros-local-ollama/BUILD_PROVENANCE.txt`.

The persistent Ollama process runs as UID/GID 10001. A network-disabled one-shot Compose service
repairs ownership of an existing `careeros-local-models` volume with only `CAP_CHOWN`, a read-only
root filesystem and no-new-privileges, then exits before Ollama starts. The running server drops
all capabilities and never receives root authority.

CI builds the image, starts the real server under the hardened runtime flags, waits for
`ollama list`, checks the patched version, emits a CycloneDX inventory and runs a HIGH/CRITICAL Trivy gate
without an ignore file or filtered baseline. The raw report is retained even when the gate fails.

## Active dependency exceptions

### CE-2026-001: `glib` 0.18.5 / RUSTSEC-2024-0429

- **Status:** Temporarily accepted. This is an active risk, not a clean Cargo audit.
- **Owner:** Project maintainers.
- **Recorded:** 2026-07-19.
- **Next review and hard expiry:** 2026-10-19. The exception must be renewed with fresh evidence or removed by upgrading before this date.
- **Advisory:** [RUSTSEC-2024-0429](https://rustsec.org/advisories/RUSTSEC-2024-0429.html) / GHSA-wrw7-89jp-8q8g. The affected `glib::VariantStrIter` implementations can dereference a null pointer and crash.
- **Scope:** Linux desktop builds only. `glib` enters the target-specific graph transitively through Tauri 2.11.5, wry 0.55.1, WebKitGTK, and the archived GTK3 bindings. Windows and macOS builds do not use this GTK3 path. CareerOS neither declares `glib` directly nor calls `VariantStrIter`.
- **Why no supported upstream upgrade exists yet:** The advisory is patched in `glib` 0.20.0, but the latest compatible Tauri and wry releases still constrain the Linux GTK3 graph to `glib` 0.18.x. Forcing 0.20 would mix incompatible gtk-rs generations and is not a safe application-level patch.
- **Audit behavior:** `cargo audit` reports this advisory as `unsound` but exits successfully by default. CI therefore uses `--deny unsound`, ignores only `RUSTSEC-2024-0429`, and fails for any other unsound advisory. The exception expiry is checked separately and fails CI on or after 2026-10-19.
- **Compensating controls:** Cargo dependencies remain lockfile-pinned; CI and release workflows run the scoped audit command, locked Rust builds, tests, license checks, SBOM generation, and an all-target dependency-tree snapshot; Dependabot continues to surface the advisory; and the application does not directly expose or invoke the affected iterator API.
- **Exit criteria:** Upgrade as soon as a supported Tauri/wry Linux backend removes the GTK3 dependency or accepts a patched `glib`, then remove this exception after Linux build, test, package, and audit gates pass.

## Monitored Rust maintenance warnings

- **Status:** Monitored upstream maintenance debt, not vulnerability exceptions.
- **Owner and next review:** Project maintainers; review by 2026-10-19 with the active dependency exception.
- **Current inventory:** RUSTSEC-2024-0370, RUSTSEC-2024-0411 through RUSTSEC-2024-0420, RUSTSEC-2025-0075, RUSTSEC-2025-0080, RUSTSEC-2025-0081, RUSTSEC-2025-0098, and RUSTSEC-2025-0100.
- **Scope:** The GTK3 and `proc-macro-error` warnings enter through the Linux Tauri/wry stack. The `unic-*` warnings enter through Tauri's `urlpattern` dependency.
- **Evidence and exit:** Every CI and release audit stores the complete Cargo audit JSON alongside the exception manifest and all-target dependency tree. Remove warnings through supported Tauri/wry updates and review any changed inventory before release.
