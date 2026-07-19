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

## Active dependency exceptions

### CE-2026-001: `glib` 0.18.5 / RUSTSEC-2024-0429

- **Status:** Temporarily accepted. This is an active risk, not a clean Cargo audit.
- **Owner:** Djenis Ejupi, project maintainer.
- **Recorded:** 2026-07-19.
- **Next review and hard expiry:** 2026-10-19. The exception must be renewed with fresh evidence or removed by upgrading before this date.
- **Advisory:** [RUSTSEC-2024-0429](https://rustsec.org/advisories/RUSTSEC-2024-0429.html) / GHSA-wrw7-89jp-8q8g. The affected `glib::VariantStrIter` implementations can dereference a null pointer and crash.
- **Scope:** Linux desktop builds only. `glib` enters the target-specific graph transitively through Tauri 2.11.5, wry 0.55.1, WebKitGTK, and the archived GTK3 bindings. Windows and macOS builds do not use this GTK3 path. CareerOS neither declares `glib` directly nor calls `VariantStrIter`.
- **Why it cannot be upgraded now:** The advisory is patched in `glib` 0.20.0, but the latest compatible Tauri and wry releases still constrain the Linux GTK3 graph to `glib` 0.18.x. Forcing 0.20 would mix incompatible gtk-rs generations and is not a safe application-level patch.
- **Compensating controls:** Cargo dependencies remain lockfile-pinned; CI and release workflows run `cargo audit`, locked Rust builds, tests, license checks, and SBOM generation; Dependabot continues to surface the advisory; and the application does not directly expose or invoke the affected iterator API.
- **Exit criteria:** Upgrade as soon as a supported Tauri/wry Linux backend removes the GTK3 dependency or accepts a patched `glib`, then remove this exception after Linux build, test, package, and audit gates pass.
