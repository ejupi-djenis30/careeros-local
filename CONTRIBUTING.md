# Contributing to CareerOS Local

Thanks for helping improve a private, local-first career workspace. Small, focused changes with
clear verification are easiest to review.

## Development setup

Follow the locked setup in [docs/development.md](docs/development.md). Use Python 3.12 and Node.js
24 LTS; native desktop work also requires Rust stable and the Tauri prerequisites.

## Before opening a pull request

1. Create a focused branch from `main`.
2. Keep personal career data, databases, logs, generated documents and secrets out of Git.
3. Add or update tests for behavioral changes.
4. Run the relevant Python, React and Rust gates documented in the development guide.
5. Update architecture, privacy or demo documentation when the public contract changes.

## Product guardrails

- Never add a cloud-model fallback or silently transmit Career Vault data.
- Keep network job sources separate from local inference.
- Preserve provenance and verification status when transforming career facts.
- Treat archives, erasure and authentication changes as security-sensitive.
- Use fictional profiles for examples, screenshots and recordings.

## Reporting security issues

Do not open a public issue for a suspected vulnerability or exposed private data. Follow
[SECURITY.md](SECURITY.md) instead.
