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
