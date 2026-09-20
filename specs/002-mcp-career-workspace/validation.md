# Validation Evidence: Feature 002

## Final verified state — 2026-09-13 19:19 Europe/Zurich

Feature 002 is implemented and passes its local acceptance gates. Tests used fictional records,
in-memory SQLite or databases/directories under the operating-system temporary directory. No test
used the real CareerOS vault or modified `../Career`.

Environment: Windows 11 ARM64; repository `.venv` Python 3.12.13 x64; Ruff 0.16.0;
Mypy 2.3.0; Pytest 9.1.1; Node 24.18.1/npm 11.16.0; Rust/Cargo 1.96.0 ARM64.

## Required gates

| Gate | Final observed result |
| --- | --- |
| `ruff check backend tests/backend` | Passed |
| `mypy backend --ignore-missing-imports --no-error-summary` | Passed |
| `pytest tests/backend -q -rs -p no:cacheprovider` with isolated settings | **2581 passed, 17 skipped, 0 failed** in 1205.39 s |
| Opt-in backend performance suite | **4 passed** in 15.80 s |
| `npm test` | **602 Vitest tests in 88 files passed**; 4 Node-version and 9 license/distribution/icon contract tests passed; icon subset check passed |
| `npm run lint` | Passed |
| `npm run build` | Passed with bundle budgets; entry 329,851 B raw / 104,633 B gzip, initial 440,597 / 138,807, workspace CSS 432,533 / 71,909 |
| `npm run test:e2e` | Passed all seven configured browser journeys |
| `cargo fmt --check` | Passed against the real Tauri resource configuration |
| `cargo clippy --offline --locked --all-targets -- -D warnings` | Passed against the real Tauri resource configuration |
| `cargo test --offline --locked` | **28 passed, 0 failed**; binary/doc targets had 0 tests |
| Alembic `upgrade head; downgrade -1; upgrade head` | Passed on a disposable database; final head `b3c4d5e6f7a9` |
| Current-source sidecar build and verification | Passed after the final resolver correction; schema-2 inventory has 1008 files, 105,638,127 bytes, target `x86_64-pc-windows-msvc`, runtime SHA-256 `f5c1148169af1c7b9fe36b8f186e04eeb201b5166634e84578a1b3be84a1e6a3` |
| Frozen packaged MCP smoke | Passed: six tools, stdio initialize, same-port restart, different-port restart and missing-descriptor fail-closed behavior |
| `git diff --check` | Passed on the final implementation/specification tree |

The 17 skips in the full backend run were reported exactly: 13 POSIX owner/mode/link/FIFO/fcntl
contracts cannot run on Windows, and four performance tests require `RUN_PERFORMANCE_TESTS=1`.
Those four performance tests were then run separately and all passed. Readiness measured p95
32.426 ms against a 100 ms budget. The 10,000-record read benchmark measured profile p95 9.413 ms,
application-page p95 67.596 ms and agenda p95 153.712 ms against a 200 ms budget. The full run's
853 warnings and the performance run's four warnings were all PyJWT
`InsecureKeyLengthWarning` instances caused by the synthetic 22-byte test key; no warning originated
in the new CareerOS code.

## Focused behavior and security evidence

Focused runs overlap and therefore are not summed into a synthetic total:

- Versioned discover/analyze/materials golden set plus the existing AI suite: **206 passed**.
  Declared golden metrics include schema validity, hard-gate/ranking correctness, evidence
  coverage and unsupported-claim recall 1.0.
- Final portability review: **145 passed**, including archive v1–v7 compatibility, strict nested
  JSON types, ownership/remapping, inactive restored authority, packet bytes and rollback.
- Agent work plus desktop/workspace MCP integration: **133 passed**. A separate independent MCP
  audit passed **121** cases, and the final descriptor/vault regression set passed **38**.
- Application/resume/automation integration group: **397 passed**.
- The five stale integration contracts discovered by the first complete gate were corrected and
  rerun directly: **5 passed**. The subsequent clean full backend run passed.
- The pre-merge PM001–PM005 regressions first failed in the expected seven cases, then passed as a
  108-case focused group. Independent review found one remaining PM001 version-without-preset edge
  case; the resolver test now passes eight cases covering locale mismatch, version-only and empty
  preset IDs, and the frozen full suite includes all final regressions.

The MCP tests use the official SDK over memory/stdio as well as the frozen console executable.
They exercise tool listing and closed input/output schemas, scope metadata, bounded context,
submission, revocation/expiry/cancellation, safe errors, total deadlines, slow request bodies,
restart-aware descriptors and zero HTTP calls for malformed input. Independent review reproduced
the critical boundaries after correction and reported no significant open finding.

## Frontend and complete journeys

The browser suite passed:

- responsive portfolio at 15 widths;
- application agenda at four widths with DST and contrast checks;
- login at 390, 1280 and 1440 pixels;
- Agent Access lifecycle, keyboard/WCAG behavior and one-time secret erasure in EN/IT at 320,
  390 and 1440 pixels;
- Agent Workspace discovery → review → acceptance in EN/IT at 320, 390 and 1440 pixels;
- a real local application-material journey that reopened generated documents, verified the ZIP
  manifest and retained the application's unsent state;
- shell geometry and reduced motion at four widths.

After the final backend resolver correction, all seven browser journeys were rerun against the
frozen source tree and passed again in 90.28 seconds.

## Document rendering and visual QA

Automated quality tests render all nine immutable presets to PDF and DOCX. They verify A4 media,
page budgets, all visible text, semantic reading order, table traversal, Unicode diacritics,
actual safe hyperlinks, optional/oversized photos, placeholders, long-content overflow,
publication hashes and template switching/restore behavior.

Five additional fictional PDFs were rendered through the production code, converted to PNG with
Poppler at 130 DPI and inspected at original resolution:

| Fixture | Layout/language | Pages | Extracted characters | Visual result |
| --- | --- | ---: | ---: | --- |
| `cv-ats-software-en.pdf` | ATS single column / EN | 1 | 504 | Clean reading order, margins and link wrapping |
| `cv-swiss-photo-en.pdf` | Swiss sidebar / EN | 1 | 491 | Clean two-column separation; no color-only dependency |
| `cv-operational-de.pdf` | Swiss operational / DE | 1 | 505 | Clean compact hierarchy and German headings |
| `letter-software-en.pdf` | Paired software letter / EN | 1 | 470 | Clean address/body/signature and hyperlink |
| `letter-operational-de.pdf` | Paired operational letter / DE | 1 | 501 | Clean German glyphs, spacing and signature |

No clipping, overlap, blank overflow page, black square, broken glyph or unresolved placeholder
was visible. QA outputs remain outside the repository in OS temporary storage.

## Corrections found during final integration

The first complete post-change gate exposed five stale repository contracts: the historical
OpenAPI grant schema still listed four scopes, two migration tests still expected the old head,
the README had dropped hash-locked legacy wheel installation steps, and the new MCP guide was not
in the approved documentation inventory. The contracts, docs and tests were updated; their direct
rerun and the clean 2571-test full suite both passed. An earlier run with `DATA_DIR` left in the
environment was discarded because it contaminated tests that intentionally construct default
`Settings()` values.

The owner-requested pre-merge audit then exposed five bounded issues: inconsistent template
tuples, quarantine of a current accepted external analysis in application snapshots, missing CLI
disclosure propagation, permissive duplicate-key decoding in nested packet manifests and a
personal absolute path in validation evidence. Regression tests were written before correction.
The first independent re-review found one additional version-without-preset case inside the same
template issue; it too failed before the fix. A second re-review reported zero P0–P2 findings.

A diagnostic full backend run overlapped the resolver edit and reported **2577 passed, 17 skipped,
1 failed**: the wheel reproducibility test copied the source once before and once after the edit, so
its two digests differed. That non-frozen run was invalidated. On the frozen tree the same wheel
test and the complete **2581-test** suite passed.

## Limits recorded without overclaiming

- The current frozen Python runtime is Windows x64 and was exercised under Windows ARM64
  emulation. The Rust/Tauri code was compiled and tested natively for ARM64, but a native ARM64
  Python sidecar was not built from the x64 virtual environment.
- Thirteen POSIX-specific backend contracts remain skipped on Windows. Native macOS/Linux CI must
  execute those and the corresponding installer/package jobs before release.
- Release signing, SBOM publication, vulnerability scanning and installer publication were not
  run because no release was requested. No live Codex/Claude account or real private vault was
  used; actual SDK/stdio/frozen-process tests use synthetic data instead.

The owner authorized a local commit and fast-forward merge into `main` after these checks. No push,
pull request, installer publication or release was performed.
