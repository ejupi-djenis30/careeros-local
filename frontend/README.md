# Frontend and desktop shell

`frontend/src` is the React 19 workspace. `frontend/src-tauri` is the Tauri 2 native shell and bundled sidecar lifecycle.

## Principles

- Keep feature components small and state local unless several routes truly share it.
- Use the centralized API client; desktop bootstrap configures its authenticated loopback base URL.
- Use native dialog and scoped filesystem plugins only through `src/platform/desktop.js`.
- Browser mode must keep a safe fallback for development.
- Do not add external fonts, analytics, remote assets, remote AI UI, or unrestricted Tauri permissions.
- Resume canvas edits must preserve immutable published versions and the typed canvas schema.

## Commands

```powershell
npm ci
npm run tauri:dev
npm test
npm run lint
npm run build
cargo fmt --manifest-path src-tauri/Cargo.toml --check
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path src-tauri/Cargo.toml
```

`npm run tauri:build` freezes the Python sidecar before invoking Tauri packaging. Generated `dist`, `target`, `.artifacts`, and sidecar build directories are never source files.
