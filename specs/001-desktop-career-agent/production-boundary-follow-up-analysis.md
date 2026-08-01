# Production boundary follow-up analysis

## Scope and method

This follow-up audited the renderer session/recovery path, desktop bootstrap, native-to-sidecar
lifecycle, managed-model launch, provider navigation, package smoke scripts and release evidence.
It reused the existing lifecycle, accessibility, session and renderer requirements, then added the
explicit external-navigation/provider-origin and artifact-retention requirements in FR-098/FR-099.
No persistence model, migration, remote inference path or background service was added.

## Reproduced gaps

- One cancelled protected request remained blocked on another request's shared refresh, and the
  refresh itself had no independent bound.
- A desktop readiness `fetch` and its response body could outlive the 90-second owner or a React
  Strict Mode cleanup.
- Recovery, failed logout and failed desktop boot replaced private/full-screen content while focus
  remained on `body`.
- The managed model process inherited desktop session, vault signing, automation, database, proxy
  and host credential variables.
- macOS/Linux package smoke failures skipped the orphan check; the Windows check ran only on the
  success path.
- Job/application data could open HTTP loopback URLs and Tauri granted the broader default opener
  scope. Job-Room followed redirects and inherited proxy environment variables without an exact
  per-request origin check.
- CI and intermediate release artifact uploads inherited GitHub's default retention.
- `THIRD_PARTY_NOTICES.txt` was stale after the locked Rust dependency graph changed.

Two Semgrep subprocess findings were reviewed manually. `scripts/run_desktop.py` builds an argv
list from constrained command choices and a resolved manifest path; `scripts/smoke_packaged_backend.py`
executes the explicitly supplied local binary with an argv list and `shell=False`. Neither finding
provided shell interpolation or an injection path, so no cosmetic suppression or code change was
introduced.

## Bundle evidence

The fresh production build contains one login stylesheet and one lazy authenticated-workspace
stylesheet. A PostCSS rule audit found 1 exact shared rule (28 approximate bytes), the terminal
`to{transform:rotate(360deg)}` step of separate keyframes, across 3,989 compiled rules. It found no
duplicated Bootstrap rule set. The executable validator now requires one initial stylesheet,
requires the isolated `careeros-bootstrap` layer only in the lazy workspace asset and applies
tighter 210,000/43,000-byte login CSS and 245,000/33,000-byte workspace CSS raw/gzip ceilings.

Measured production output under Node 24.18.0:

| Surface | Raw | Gzip | Ceiling raw/gzip |
|---|---:|---:|---:|
| Entry JavaScript | 325,676 B | 103,172 B | 350,000 / 112,000 B |
| Largest locale | 74,816 B | 23,869 B | 82,000 / 26,000 B |
| Login CSS | 196,856 B | 40,387 B | 210,000 / 43,000 B |
| Worst-case login | 598,395 B | 167,994 B | 660,000 / 185,000 B |
| Lazy workspace CSS | 230,877 B | 30,598 B | 245,000 / 33,000 B |
| Workspace shell JS | 28,212 B | 8,349 B | 32,000 / 9,600 B |

`THIRD_PARTY_NOTICES.txt` is a distributed legal resource, not a renderer request. It was
deterministically regenerated to 1,385,908 bytes with SHA-256
`daca71a49feb42bb1428053aa64cc1d6d4ea5c97da73d8015cca58dbabd0ca04`.

## Verification evidence

- Node 24.18.0 `npm test`: 78 Vitest files and 468 tests passed; 4 runtime-contract tests, 6
  license/distribution tests and the 123-icon drift check also passed.
- Node 24.18.0 `npm run lint`: passed.
- Node 24.18.0 `npm run build`: passed with every raw/gzip budget and lazy-CSS isolation assertion.
- Focused Python provider, inference, release, notice, distribution and repository selection:
  124 tests passed.
- Focused Ruff and Mypy checks for changed Python production/test surfaces: passed.
- `python -m scripts.third_party_notices --check`: passed with 12 frontend, 55 Python, 2 runtime
  and 484 Rust components.
- `cargo test --locked --lib`: 19 tests passed and regenerated the scoped capability manifest.
- `cargo clippy --locked --all-targets -- -D warnings`: passed.
- `git diff --check`: passed.

## Limits

No real MSI, NSIS, DMG, AppImage or Debian package was installed in this follow-up, and no backend
service or user port was started. Package cleanup coverage is synthetic plus Rust lifecycle coverage;
the release matrix remains the authority for real operating-system smoke. `cargo fmt --check` could
not start because Windows Application Control blocked `cargo-fmt` (OS error 4551); no Rust source was
changed in this follow-up, while Rust compilation and Clippy both passed.
