# Validation evidence: Production Readiness Refactor

Date: 2026-10-16. Branch: `codex/production-readiness-refactor`.
Release eligibility: **blocked** by the complete frontend vulnerability scan.
This is source maintenance evidence, not a signed release or installer acceptance.

## Changes and review

- Removed 433 net lines of duplicated AI scaffolding; class AST comparison preserved
  production method behavior, with the trivial query-fingerprint wrapper inlined.
  Legacy exports and monkeypatch forwarding remain covered by 214 focused tests.
- Resume Studio now binds completions to a mounted editor session, orders loads,
  serializes same-session operations, and merges only fields edited after each
  request. Stale local errors, global error events, photo responses and toasts are
  ignored. Delayed requests, StrictMode and same-session edits have regressions.
- Browser backup export uses the shared download implementation. Desktop build
  commands use installed tools, preflight Rust targets and enforce Cargo locks.
  Hooks use the reviewed development environment and do not install dependencies.
- Runtime security pins: MCP 1.30.0, PyJWT 2.15.1, pypdf 6.21.0. Development fixes:
  urllib3 2.8.0, virtualenv 21.13.0 and its required python-discovery 1.6.3.
  Packaging tooling uses pip-tools 7.6.1 for compatibility with pinned pip 26.2.
  Other resolved versions remain unchanged. Updated artifact hashes were checked
  independently against official PyPI metadata, including non-yanked status and
  supported Python versions. Windows-only pywin32 markers remain intact.
- Independent review identified and corrected same-session mutation interference,
  global stale error events, lockfile LF reproducibility, and license inventory
  omission of extra-qualified HTTPX/PyJWT requirements. The last inventory fix
  follows FR-010 and T015. Normal generation now includes all 57 Python components;
  the three distribution contract tests also require HTTPX and PyJWT identities.

## Completed checks

The source runtime is exact Python 3.12.13 in an OS temporary environment, restored
with hash verification from the final development lock. Node is 24.18.1 and Rust
is 1.96.0. Earlier setup checks used compatible Python 3.12.14; these are not
substituted for final checks against the updated dependency environment.

| Check | Executed result |
| --- | --- |
| Desktop wrapper and hook regressions | 14 passed |
| Source desktop lifecycle tests, final Python environment | 32 passed, 6 skipped; reasons below |
| Complete backend coverage gate, final Python environment | 2,840 passed, 17 skipped in 1,200.90 seconds; combined statement/branch coverage 81.96%, exceeding the 80% gate |
| Opt-in backend performance gates, without coverage | All 4 passed in 9.88 seconds; measured budgets below |
| Native `cargo fmt --check` | Passed |
| Native `cargo clippy --locked --all-targets -- -D warnings` | Passed |
| Native `cargo test --locked` | 28 passed; no failures |
| Native `cargo deny --all-features check licenses` | Passed |
| Native `cargo audit --deny unsound --ignore RUSTSEC-2024-0429` | Passed with the existing approved exception and 6 allowed unmaintained-package warnings |
| Release version consistency and security exception policy | Passed; version 1.11.1 / 2026-08-01 consistent across seven sources; existing exception checked as of 2026-10-16 |
| Migration `upgrade head`, `downgrade -1`, `upgrade head` | All passed on a new temporary database with the final Python environment |
| Frontend final complete coverage run | 96 files / 653 tests passed; statements 82.15%, branches 73.02%, functions 74.24%, lines 86.93%; all configured thresholds passed |
| Frontend lint and production bundle budgets | Passed after final editor/photo changes and the complete regenerated notices |
| Frozen source Ruff and mypy, including scripts | Both passed |
| Canonical notice reproduction and inventory | Passed with exact Python 3.12.13; 12 frontend, 57 Python, 3 runtime, 484 Rust components; all required lock bytes LF |
| Frontend E2E aggregate | All 7 groups passed: portfolio, agenda, login, agent access, agent work, real API material journey, responsive shell |
| Real API material journey after Python security updates | Repeated successfully with exact Python 3.12.13 and final notices; generated documents verified |
| Isolated agent wheel packaging/install/protocol smoke | Passed from a temporary source snapshot: clean hash-locked runtime install, `pip check`, CLI entrypoints, empty-vault diagnostics, stdio MCP initialization and least-privilege tool list |
| Python runtime/development/tooling lock vulnerability audits | All three passed, zero known vulnerabilities after the security updates |
| Frontend production-only vulnerability audit | Passed, zero vulnerabilities in production dependencies |
| Complete frontend vulnerability audit | **Failed**, 11 development dependency nodes: 7 high, 4 moderate |

All final source gates have completed. Backend statement coverage is 84.55% and
branch coverage is 73.26%; the configured combined coverage is 81.96%. No source,
frontend dependency or notice changes followed the complete final checks.

Performance gates used the exact final Python environment without coverage:

| Scenario | Result | Required budget |
| --- | --- | --- |
| Deterministic resume generation from 1,000 facts | Passed | <500 ms |
| Detailed resume reads, 30 samples after warmup | Passed | p95 <200 ms |
| Profile / 200-row application page / 50-row agenda, 10,000 applications | p95 6.064 / 40.711 / 95.361 ms | Each p95 <200 ms |
| Verified DOCX/PDF readiness, 300 facts, 3 rounds of 30 samples | Median round p95 22.543 ms; maximum 5 queries | <100 ms; <=5 queries |

No benchmark threshold was changed. Measurements describe this workstation;
they do not establish performance across supported hardware profiles.

Final notice SHA-256:
`bb7457f3a095fbdc9981c869c08027af95fddaf8e38bbd3ca199196a450430b0`.

Desktop skips: five Windows-inapplicable POSIX ownership/no-follow checks in
`tests/desktop/test_backend_entry.py` (lines 194, 207, 230, 531, 614), and one
packaged lifecycle acceptance test requiring `CAREEROS_SIDECAR_BINARY`.

Backend skips: 13 Windows-inapplicable POSIX contracts (migration ownership,
atomic hard-link/ctime/FIFO behavior, database ownership/no-follow/link ownership,
SQLite ownership/fcntl) and four opt-in performance tests, run separately without
coverage. No backend test failed.

The six Rust unmaintained warnings are proc-macro-error and the five unic packages
unic-char-property, unic-char-range, unic-common, unic-ucd-ident, unic-ucd-version.
The existing glib exception expires on 2026-10-19 and was not extended.

## Frontend release blocker

Affected development nodes are `@eslint/config-array`, `@eslint/eslintrc`, ESLint,
minimatch, brace-expansion, js-yaml, source-map-js, undici, Vitest,
`@vitest/mocker` and `@vitest/coverage-v8`. Every node is marked development-only
in the lock; the full scan still blocks release under constitution VII.

The official advisory fixed versions were checked against the official npm
registry with fresh metadata requests. Required versions were unavailable (404):
Vitest 4.1.11, brace-expansion 5.0.12, source-map-js 1.2.2, js-yaml 5.4.1 / 4.3.2,
and undici 7.29.1 / 8.10.2. All nine package/version checks still returned E404 at
23:11:51 Europe/Zurich on 2026-10-16. A temporary js-yaml 4.3.1 trial introduced an additional
high advisory; it was reverted. The final frontend manifest and lock retain their
original dependency content. No incompatible downgrade, audit suppression or new
exception was introduced.

Primary advisory references:
[Vitest](https://github.com/advisories/GHSA-82fw-gwwq-j7x9),
[brace-expansion](https://github.com/advisories/GHSA-q2hr-2g5m-vwhr),
[js-yaml 5](https://github.com/advisories/GHSA-r3ph-w7gj-g6xm),
[js-yaml 4](https://github.com/advisories/GHSA-2883-xcg3-v3hh),
[source-map-js](https://github.com/advisories/GHSA-68fv-2mgg-jv7q),
[undici](https://github.com/advisories/GHSA-w293-vg96-wgc3).

## Earlier attempts and limits

The first E2E aggregate failed at login with a 404 while a concurrent Vite build
was recreating `dist`. The isolated login test and complete sequential aggregate
then passed. README/development instructions now require build before E2E and
prohibit running them simultaneously. No product or harness workaround was added.

Two initial backend coverage attempts were interrupted when dependency locks and
license inventory changed, to avoid presenting a mixed source snapshot as final.
The next attempt exposed migration fixture errors because the invocation set a
process-wide `DATA_DIR` while the fixtures explicitly own separate temporary
databases. A controlled comparison reproduced containment rejection with that
environment variable and passed the identical three-test probe without it. This
was an invocation error, and no security guard or production code was changed.
The final suite removes process database/data overrides, uses the in-memory test
database, and directs the application settings data root, pytest output and
coverage to OS temporary paths. A separate diagnostic probe initially omitted
the parent of its explicit pytest base directory and stopped after 96 passes;
that probe is not presented as a successful gate.
An initial `uv pip sync -r` invocation failed argument parsing without modifying
packages; the positional-file invocation completed with hash verification.

Native installers, clean-machine install/restart/upgrade on Windows/macOS/Linux,
signed artifacts, artifact SBOM/provenance, container image scans, and hardware
local-model evaluation have not been executed in this
maintenance run. No artifact is represented as signed or production-approved.

The temporary wheel smoke produced an unsigned, automatically removed test wheel:
`careeros_local-1.11.1-py3-none-any.whl`, 1,009,760 bytes,
SHA-256 `42d3c49923a3dcd79e39d009ab12118ec701546c6efa59e0d6691b4d9882508d`.
No release artifact was retained or published.

## Cleanup inventory

No tracked temporary dump, log, backup, binary or command-output directory was
identified in the initial 1,245 tracked files. No user data or source artifact was
deleted. `.agents`, `.specify`, active/historical specifications and `../Career`
were preserved; the reference directory and personal runtime data were not read.
Ruff cache and local Serena memories are now ignored. Environments, database
roundtrips, command JSON and synthetic QA material use the OS temporary directory.
Frontend build/coverage outputs and node_modules remain ignored development
outputs; no generated command output was added to source.

Automatic approval review rejected the initial computed recursive cleanup command
with the reason `blocked by policy`; that command did not execute. A safer explicit
nonrecursive deletion of the three inventoried Ruff cache files (570 bytes), then
their empty parent directories and the two verified empty task-created directories
(`data` and `frontend/src-tauri/binaries/careeros-backend-runtime`), completed
successfully. Absence of all three generated directory targets was verified.
