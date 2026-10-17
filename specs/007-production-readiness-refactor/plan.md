# Plan: Production Readiness Refactor

## Constitution check

Reviewed constitution 2.0.1 before implementation; no amendment is needed. Retain
local canonical data, explicit network acquisition, validated local inference,
draft-only external authority, loopback authentication, vault lock, atomic writes,
archive containment, migrations, and secret-free diagnostics. No persistent
schema changes are planned.

## Audit and decisions

The initial worktree is clean on `main`; work proceeds on
`codex/production-readiness-refactor`. Read-only audits cover backend, React/Tauri,
and release infrastructure. No tracked dump/log/temp artifact was identified;
cleanup targets generated caches only after containment verification.

1. Add an editor-session epoch to Resume Studio. Every asynchronous completion
   checks its originating session; overlapping loads additionally use request
   ordering. Keep within-session edit sequence semantics for autosave. Prefer a
   focused helper if needed rather than growing a compatibility facade.
2. Remove duplicated unused private AI retry/fingerprint helpers after checking
   references. Retain legacy facade exports and patch forwarding. Remove blanket
   unused-import suppression where imports can be explicit and auditable.
3. Reuse `frontend/src/lib/download.js` for browser backup download lifetime.
4. Harden `scripts/run_desktop.py` and pre-commit entry points: local-only CLI,
   target preflight, Cargo `--locked`, reviewed tool pins, complete CI type scope.
   Test missing tools/targets and command construction without starting a build.
5. Ignore generated Ruff/Serena caches without ignoring tracked development
   infrastructure. Never run broad `git clean` or delete private runtime paths.
6. Initial vulnerability audits found known issues in MCP, PyJWT, pypdf, urllib3,
   virtualenv and frontend tooling/transitive packages. Verify upstream fixed
   versions, update the minimum necessary declared pins/overrides and hash locks,
   regenerate notices as required, and rerun security, auth, MCP, document and
   frontend regressions with the final dependency environment.
7. Independent review found the notice requirement parser silently omitted locked
   distributions declared with extras. Extend its strict grammar to canonical
   optional extras, reject malformed records, add inventory regressions for HTTPX
   and PyJWT, normalize required LF lockfiles, and regenerate complete notices
   through the existing exact Python toolchain. Never substitute a hand-edited
   notice or weaken digest checks.

## Validation

Use a supported Python 3.12/3.13 environment and Node 24.18.x; the default PATH
Python is 3.14 and must not validate the application. Restore reviewed development
dependencies explicitly if needed, keeping the Python environment and command
output in the OS temporary directory. Run focused regressions before full gates:

```
ruff check backend tests/backend scripts
mypy backend scripts --ignore-missing-imports --no-error-summary
pytest tests/backend -q
npm test
npm run lint
npm run build
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Migration commands use a fresh temporary data root, never the desktop vault.
Review changes independently, analyze artifact coverage, then converge remaining
work. Record failures, missing environment prerequisites, skipped acceptance,
signing and packaging limitations instead of describing source checks as a release.

## Existing size exceptions

The audit identified existing large application/domain/native modules. Unrelated
decomposition is deferred because file length alone is not a defect. This pass
reduces repeated AI scaffolding and fixes measured asynchronous/build boundaries.
Future decompositions of restore, managed runtime, application dossier, and native
lifecycle must retain their existing focused failure and recovery tests; no new
oversized compatibility facade is introduced.
