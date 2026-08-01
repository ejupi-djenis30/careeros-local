# Measured offline renderer boot — analysis

Date: 2026-07-30

## Scope and baseline

This slice closes the informational Vite warning left by the mobile-navigation review through
measured startup-byte reduction. It keeps both supported languages and every production icon
inside the offline distribution, but removes assets that the login route does not need at boot.
It also closes configuration findings discovered while reviewing the same distribution boundary.

The unoptimized production build measured:

| Asset | Raw | Gzip or transferred |
| --- | ---: | ---: |
| Initial JavaScript entry | 505,230 B | 153,470 B gzip |
| Initial CSS | 434,093 B | 67,400 B gzip |
| Bootstrap Icons WOFF2 request | 134,044 B | 134,044 B transferred |
| Combined eager language source | 191,349 B | Included in the entry |
| Browser-observed login resources | approximately 1.076 MB | approximately 355 KB gzip-equivalent |

The baseline had no meaningful cumulative layout shift or long tasks, so the intervention targets
transfer, parsing and enforceable quality contracts rather than claiming an interaction-latency
regression that was not observed.

## Findings

1. English and Italian were exported from one eager module. The selected language setting changed
   messages after boot but could not prevent both catalogues from entering the initial graph.
2. Importing the complete Bootstrap Icons stylesheet emitted a 134,044-byte WOFF2 file plus a
   180,288-byte fallback font even though production JSX uses a finite set of explicit icon names.
3. `frame-ancestors 'none'` appeared in the HTML meta policy. Browsers do not enforce that directive
   from a meta policy; Nginx already owns the effective response-header policy.
4. The inactive language control measured 3.79:1 and the privacy line 3.98:1 at the real mobile
   login viewport. Language controls were also smaller than the 44 px touch target used elsewhere.
5. Release workflow repository, tag and commit expressions entered shell command arguments
   directly; the reverse proxy reflected the client-supplied Host; routine Dependabot updates had
   no explicit review cooldown.
6. A first asynchronous implementation exposed two failures only visible against the real
   production graph: StrictMode cleanup could leave a remounted provider marked inactive, and an
   early failure return made hook order conditional. Both were corrected before acceptance.

## Implemented behavior

- English and Italian now compile to independent local chunks behind a registry that deduplicates
  pending imports. Initial boot requests only the persisted language; Italian failure falls back to
  English. A dual failure shows a statically localized, focused retry without automatic reload or
  request loop.
- Both language controls become busy and disabled while an unloaded catalogue is pending. A
  catalogue already in memory switches synchronously, preserving existing interaction behavior.
- The eager `messages.js` aggregation remains available only to tests that verify catalogue parity;
  production code has no import path to it.
- A deterministic generator scans explicit `bi-*` tokens, verifies the corresponding upstream SVG,
  and emits 123 MIT-attributed CSS masks. Computed or missing icon names and stale generated output
  fail the test gate. No icon WOFF or WOFF2 enters `dist`.
- The production build now enforces raw and gzip ceilings for the entry, largest selected locale,
  CSS and worst-case login resources. The warning was removed by byte reduction, not cosmetic
  `manualChunks` relocation.
- Real Chromium at 390 × 844, dark theme and reduced motion verifies independent English and
  Italian boot, live language switching, zero font requests, icon rendering, 44 px targets,
  keyboard focus, disabled submit behavior, WCAG A/AA/2.1 AA axe results and a clean console.
- The ineffective meta `frame-ancestors` directive was removed. The Nginx response header retains
  `frame-ancestors 'none'` and `X-Frame-Options: DENY`; Tauri's native CSP is unchanged.
- Every managed Dependabot ecosystem now applies a seven-day default cooldown. Security updates
  remain outside GitHub's routine-update cooldown semantics.
- Release repository, tag and commit values are bound once as workflow environment variables and
  passed as quoted runtime values. The cross-platform candidate step declares Bash explicitly.
  Nginx now sends the allowlisted upstream Host `localhost`.

## Measured result

| Asset or scenario | Final | Change from baseline |
| --- | ---: | ---: |
| Initial JavaScript entry | 340,810 B raw / 107,495 B gzip | −32.5% raw / −30.0% gzip |
| English session JavaScript | 421,614 B raw / 130,315 B gzip | −16.6% raw / −15.1% gzip |
| Italian session JavaScript | 427,500 B raw / 131,718 B gzip | −15.4% raw / −14.2% gzip |
| Largest selected locale | 86,690 B raw / 24,223 B gzip | Independently loaded |
| Initial CSS | 420,637 B raw / 69,843 B gzip | −3.1% raw; +2.4 KB gzip for embedded SVG masks |
| Icon font requests | 0 | −134,044 B WOFF2 request |
| Worst-case login resources | 849,184 B raw / 202,124 B gzip | approximately −21% raw / −43% compressed transfer |

The executable ceilings are 360,000/115,000 bytes for entry raw/gzip, 90,000/26,000 for a selected
locale, 430,000/72,000 for CSS and 875,000/215,000 for worst-case login resources. All have useful
headroom and fail the build when exceeded.

The CSS gzip total increases by 2,443 bytes because the used SVG geometry is now embedded. That is
an intentional exchange for removing a separate 134,044-byte compressed font response, its
180,288-byte fallback artifact, glyph over-inclusion and font-rendering dependency.

## Validation evidence

| Gate | Exact result |
| --- | --- |
| Complete frontend suite | `npm test`: 74 Vitest files and 405 tests passed; 5 distribution/license contract tests passed; generated subset current at 123 icons |
| Frontend lint | `npm run lint`: passed |
| Production build and budgets | `npm run build`: passed with entry 340,810/107,495 B, largest locale 86,690/24,223 B, CSS 420,637/69,843 B and initial 849,184/202,124 B |
| Login browser acceptance | `npm run test:login-quality`: EN, live IT and persisted IT had zero axe violations, zero font requests and zero console/page errors; inactive language contrast 7.60:1 and privacy contrast 7.96:1 |
| Existing browser gates | Workspace shell at 4 viewports, agenda at 4 viewports plus contrast/DST, and Pages at 15 widths passed |
| Python lint and types | Full Ruff and Mypy gates passed |
| Complete backend suite | Locked Python 3.12 environment, explicit OS temporary base: 1,582 passed; 4 opt-in performance tests and 1 packaged-lifecycle test without release artifacts skipped |
| Explicit performance budgets | Isolated run: readiness 15.185 ms p95 under 100 ms with 5/5 query budget; profile 5.825 ms, application page 31.060 ms and 10k-row agenda 81.402 ms under 200 ms; 2 canvas budgets passed |
| Rust gates | `cargo fmt --check`, Clippy with warnings denied and `cargo test`: passed; 17 tests |
| Migration round-trip | Isolated SQLite: upgrade to `e7f8a9b0c1d2`, downgrade to `d6e7f8a9b0c1`, re-upgrade to head passed |
| Workflow/config contracts | PyYAML parse and Actionlint passed; release/distribution/repository-hygiene focus: 40 tests passed |
| Dependency/security review | Pip Audit found 0 vulnerabilities; Trivy reported the one existing transitive Linux glib exception; Cargo Audit found 0 other unallowed advisories and 16 unmaintained warnings; Bandit found 0 high/medium issues |
| Semgrep OWASP review | 217 rules completed; 5 timed-out files passed on the 60-second rerun; 0 new actionable findings |

Semgrep also reported two subprocess patterns. Both construct argument arrays, do not invoke a
shell and constrain the executable/input to the intentional local packaging or managed-runtime
boundary. They are false positives rather than injection paths; no blanket suppression was added.
Dependency comparison found only patch-level updates, so this performance/security slice did not
mix in unrelated lockfile churn.

The first aggregate opt-in performance rerun overlapped another subagent's full browser E2E on the
same workstation and exceeded two latency ceilings (146.139/100 ms readiness and 298.827/200 ms
agenda). It is not counted as passing. Once that process and its ports were confirmed closed, the
same tests ran separately at 15.185 ms and 81.402 ms respectively; profile, application-page and
both canvas budgets also passed. No backend implementation or benchmark threshold changed between
the contended and isolated runs.

### Transitive glib exception

The refreshed Trivy database reports medium advisory
[`GHSA-wrw7-89jp-8q8g`](https://rustsec.org/advisories/RUSTSEC-2024-0429.html) against `glib 0.18.5`.
The affected surface is the `VariantStrIter` iterator implementation; RustSec marks versions
0.15–0.19 affected and 0.20.0 as the first patched line.

This is not linked into the Windows or macOS target graph. The Linux graph reaches it through
current Tauri 2.11.5, Wry/Tao/Muda, GTK 0.18 and WebKitGTK. Tauri's official Linux prerequisites
likewise identify WebKitGTK as a Linux system boundary. A registry-wide source search found no
`VariantStrIter` call site outside glib's own definition/export. Therefore the unsafe iterator is
not reached by CareerOS or its resolved direct/transitive desktop sources in the audited graph.

A dry-run lock update to glib 0.20.0 fails because current Tauri and GTK 0.18 require
`glib ^0.18`; the current crates.io Tauri release remains 2.11.5. Updating only the lockfile cannot
fix this finding, while forcing glib 0.20 would require an incompatible GTK/WebKit/Tauri ecosystem
migration and Linux platform validation. No unsafe override or downstream fork was introduced.

The existing `CE-2026-001` exception remains narrowly scoped to
`linux-desktop-transitive`, pins the exact lockfile package, expires on 2026-10-19 and fails CI at
expiry or when the locked version changes. CI preserves the Cargo dependency tree with release
evidence and ignores only `RUSTSEC-2024-0429`. The follow-up is to adopt the first supported
Tauri/GTK line that removes glib 0.18, then delete the exception; until then the target isolation,
absence of affected call sites and hard expiry bound the practical exposure.

## Residual limits

- The complete Bootstrap CSS surface remains the largest renderer asset. It is below the enforced
  budget; modularizing it would be a separate layout-wide migration because utilities are used
  across the current product.
- Selecting a not-yet-loaded language adds one local chunk request. It remains entirely offline,
  is deduplicated, exposes pending state and has explicit recovery.
- Actionlint and contract tests validate the release workflow, but no GitHub-hosted release job,
  signed installer, frozen sidecar/platform matrix or live compact-model evaluation ran locally.
- Nginx behavior is locked by distribution tests; a containerized Nginx startup was not part of
  this Windows workstation pass.
- Linux packaging still resolves the time-bounded glib 0.18 exception described above. It is not a
  zero-advisory claim and must be re-evaluated no later than 2026-10-19.
- No commit, merge, staging, push, release or deployment was performed.
