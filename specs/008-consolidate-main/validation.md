# Validation evidence: Consolidate all work into main

Date: 2026-10-17. Initial branch: `codex/production-readiness-refactor`;
follow-up branch: `codex/final-dependency-patches`.
Status: PR #112 is merged and verified; automated frontend/Python follow-ups and final
ref cleanup are in progress. No production release or installer signing claim.
This source record captures the initial integration and precedes the follow-up's
protected publication. Subsequent live checks and Git operations complete its
remaining tasks; a pending entry is never presented as a passing check.

## Scope and review

The original refactor tree is preserved in public commit `bfbc06c` (the unpublished
local identity `6659277` is retained in the local recovery bundle). The branch ledger records
all twelve remote branch tips and their content decisions. Configurable providers
were recovered on current authentication, proposal-only agent authority and
desktop vault ownership. The old colliding migration was replaced with revision
`d0b1c2d3e4f5`, following `c0a1b2c3d4e5`.

Independent reviews identified and corrected cross-origin forwarding of saved
secret headers, provider-only backup/restore without synthetic profiles, strict
legacy archive validation, provider quotas, lost-commit-ack verification and
lazy selected-language provider resources. The fixed boundary and rollback tests
were executed before the final backend snapshot was frozen.

Verification uses exact Python 3.12.13 in a hash-synchronized temporary
environment, Node 24.18.1 and Rust 1.96.0. Persistent application data and the
reference directory `../Career` were not used. Test databases, snapshots, command
evidence, npm caches and unsigned packaging proofs are in the OS temporary area.

## Executed checks

| Check | Actual result |
| --- | --- |
| Ruff, backend/tests/scripts | Passed on final provider implementation |
| mypy, backend/scripts | Passed on final provider implementation |
| Complete backend coverage baseline | 2,936 passed, 17 skipped, 3 failed in 1,314.04 seconds; combined coverage 82.00%. Failures were stale expected command, PyInstaller identity and document allowlist contracts; corrected before final verification |
| Final local complete backend coverage gate | 2,940 passed, 17 skipped in 1,219.53 seconds; combined coverage 82.03%. Pytest returned 0; the broad freeze wrapper returned 1 solely because T014 intentionally changed the frontend E2E credential fixture during the run. Backend Python, dependency and distribution inputs were unchanged |
| First protected Linux backend gate | 2,946 passed, 11 skipped in 628.60 seconds; combined coverage 83.59%, followed by passing opt-in performance gates. This precedes T015–T017; the final PR head must repeat its required checks |
| Final PR #112 Linux backend gate | 2,947 passed, 11 skipped in 683.03 seconds; combined coverage 83.59%, followed by passing performance gates |
| Separate opt-in backend performance tests | All four passed in 9.16 seconds on final Python/provider source; 1,168 recorded inputs unchanged |
| Desktop source lifecycle tests, final Python dependencies | 32 passed, 6 skipped in 15.49 seconds; five Windows-inapplicable POSIX ownership/no-follow checks and one packaged lifecycle test requiring CAREEROS_SIDECAR_BINARY |
| Provider/network/consent boundary regressions | Passed; overlapping focused runs include 143 provider/consent/pipeline tests and 26 transport/auth/bounds tests |
| Complete portability focused gate before provider-only addition | 194 passed; followed by focused provider-only, rollback and legacy-contract regressions |
| Final provider-only and provider integration tests | 54 passed; independent review also passed real API/export and commit-ack failure reproductions |
| Final Unicode mask and boundary/contract regressions | 267 passed in 88.54 seconds: 187 provider cases plus 80 release/security contracts. Independent API expected values check POST/detail/catalog against eight U+2022 codepoints; the new regression failed before the fix |
| Frontend before final dependency integration | 101 files / 681 tests passed; statements 82.09%, branches 72.69%, functions 73.94%, lines 86.94%; all configured thresholds passed |
| Final frontend complete coverage | 104 files / 686 tests passed after the language-label correction; statements 82.12%, branches 72.71%, functions 74.01%, lines 86.96%; all configured thresholds passed, plus four Node runtime tests, nine license/distribution tests and icon checks |
| Frontend focused provider/locale/backup regressions | 51 passed |
| Frontend lint and production build before final dependency integration | Passed; initial 443,268 raw / 139,559 gzip bytes; Italian locale 89,925 raw bytes; original budgets unchanged |
| Frontend real API/browser aggregate before final dependency integration | All eight groups passed, including provider-only backup download hashed against the API response |
| Final frontend dependency integration | Original fresh-cache npm ci installed 272 packages; complete/production audits both passed with zero vulnerabilities; complete peer tree and 13 production licenses passed |
| Final router build | Lint/build passed after the accessibility fix: entry 266,593 raw / 82,794 gzip bytes; initial 379,402 / 117,598; Italian locale 89,925 raw bytes; original budgets unchanged |
| Final browser aggregate | All eight groups passed on the corrected frozen source and final build: portfolio, agenda, login, agent access, agent work, real material API journey, real provider API/backup journey and responsive shell. This includes canonical header masks and EN/IT WCAG checks at 320/390/1440 widths |
| Rust fmt / locked clippy all targets with warnings denied / locked tests | All passed; 28 native tests passed |
| Rust license gate | Passed |
| Rust vulnerability policy | Updated Tauri cohort passed with the existing glib exception and one unmaintained warning (RUSTSEC-2024-0370); no exception extended |
| Security exception policy | Passed as of 2026-10-17; existing glib exception expires 2026-10-19 |
| Version consistency | Passed: 1.11.1 / 2026-08-01 across seven sources; no release tag or version bump |
| Alembic upgrade head / downgrade one / upgrade head | All passed on a fresh temporary database; final head d0b1c2d3e4f5 |
| Runtime / development / tooling Python lock audits | All three passed, zero known vulnerabilities |
| Exact Python environment pip check | Passed |
| Independent official Python package/hash/compatibility review | Passed; common pins agree across locks and Windows-only pywin32 markers remain |
| Distribution/container/workflow focused contracts | 62 passed; Docker Compose configuration passed |
| Complete release and security contracts after metadata corrections | All 288 tests passed in 182.68 seconds. The freeze wrapper returned 1 because nine frontend language-control/test files were intentionally corrected during this run; those changes are included in the final complete backend snapshot |
| Final complete release and security contracts after T015–T017 | 289 passed in 169.68 seconds; pytest and freeze wrapper both returned 0, all 1,168 recorded inputs unchanged. Subsequent formatting of two test files was independently AST-identical and Ruff passed |
| Ollama archive and Go dependency verification | Archive checksum, module verification and all nine retained security pins passed |
| Shipping container build/smoke/vulnerability scan | Incomplete locally; see limits below |
| Isolated installed Python wheel/protocol proof | Passed using clean hash-locked runtime installation, CLI, empty-vault diagnostics and least-privilege MCP initialization |
| Installed bundled provider resource | Passed from site-packages in isolated Python: 11 providers, pack careeros.switzerland.core version 1.1.0 |
| Canonical notices after T016 | Normal generation/reproduction passed: 13 frontend / 57 Python / 3 runtime / 473 Rust components; 1,424,072 bytes, SHA-256 7baf4fe8d0068e99e3d080f05fe415f16a267b5d1172188f5cfc08381102707b. Nine Node distribution/license tests and icon checks passed; the new asset is included in the passing production build |
| Final changed-file commit hooks and diff whitespace | Passed after generated JSON final-newline normalization; initial hook correction is retained as an initial failure, followed by a complete passing rerun |

Focused test totals overlap and must not be added together. Earlier backend
whole-suite attempts were deliberately interrupted when new boundary fixes were
needed; they are not passing gates. An earlier concurrent focused portability
attempt had two stale-fixture failures during editing; final corrected focused
checks passed, and the frozen complete suite is authoritative for the final code.
The first desktop launcher used stdin and one Windows multiprocessing test could
not reopen that launcher path. Running the unchanged suite from a guarded Python
file in the OS temporary directory produced the 32-pass result above.
The complete baseline recorded 638 backend/test/script inputs with zero changes.
The three failing contract expectations were updated precisely, preserving their
checks. New dependency pins also required exact reviewed brace-expansion/router
expectations and the new MIT-licensed route-pattern identity. No synthetic
security-fixture versions or validation rules were relaxed.

The decomposition itself passed 186 focused tests on the original worktree and
independent Ruff/type/AST/schema review. All new provider production modules are
below 300 lines; 22 JSON model schemas, five aliases and complete OpenAPI output
remain deeply identical. The old provider module-size exception is unnecessary.
The subsequent real API journey exposed a mojibake top-level mask constant missed
by model/function comparisons and shared-constant expected values. The fix uses
eight explicit ASCII Unicode escapes. Independent comparison against the
preserved pre-split wheel confirms all eighteen moved global assignments and all
original string literals are now AST-identical; only the new facade docstring is
intentional. The first post-split complete run was interrupted before mutation,
then restarted on the corrected source. That interrupted run is not a pass.

Performance measurements used no coverage and changed no thresholds:

| Scenario | Actual result | Budget |
| --- | --- | --- |
| Resume generation, 1,000 facts | Passed | <500 ms |
| Resume detail reads, 30 samples | Passed | p95 <200 ms |
| Profile / 200-row application page / 50-row agenda, 10,000 applications | p95 5.176 / 42.281 / 94.093 ms | Each p95 <200 ms |
| Verified DOCX/PDF readiness, 300 facts, three rounds | Median round p95 18.596 ms, maximum five queries | <100 ms, <=5 queries |

## Package audit correction

The pre-update complete npm audit actually failed with eleven development nodes
(seven high, four moderate); its production-only audit passed with zero findings.
The old local npm cache returned E404 for patched versions even with prefer-online.
Independent fresh-cache registry checks established that those versions are now
resolvable. The unavailable-fixes conclusion is withdrawn. The installed final
lock now passes fresh complete and production audits with zero findings, plus
the complete peer tree and 13-package production license gate. Updated security
versions include Vitest/coverage 4.1.11, js-yaml 4.3.2, brace-expansion 5.0.12,
source-map-js 1.2.2 and undici 7.29.1. No audit suppression or threshold exception
was added. Final affected browser/backend gates remain explicitly tracked above.

Both frontend JSON files were normalized to LF before the final notice generation.
A notice check during that normalization failed its strict source-hash binding;
the regenerated final notice reproduced and verified successfully. Final package
and lock SHA-256 are respectively
`fe791073e605815961ee23664ac565133ee5438b4be5c291ada117bc3386e687` and
`bb88e6c7b25928c12a677640f654d3e5239685466246aa25bf430cbc7d9cec6c`.

## Packaging proof and limitations

The earlier temporary, unsigned post-mask-fix wheel was 1,043,971 bytes, SHA-256
`c1a40a91da1292c39640f55614e16b92a5e96de085727f04c333a6ef93920899`.
The installed provider pack is 12,978 bytes, SHA-256
`e1a54a751a8e71d75cb6fab12ef57489466c46ab4c00f85084c266d83e8861e3`.
Both checks used an isolated source snapshot and proved imports from installed
site-packages, rather than accidentally loading the repository. All 440 snapshot
inputs were unchanged. Standard wheel smoke passed the fresh hash-locked install,
pip check, both CLI entrypoints, synthetic empty-vault diagnostics and exactly two
system-read MCP tools. A second clean install proved the eight separated modules,
bundled JSON and final installed notice digest in isolated Python.
The installed mask and redaction helper were independently checked for eight
U+2022 codepoints. A first resource-proof invocation omitted a required synthetic
base_url; its temporary invocation was corrected and the isolated check passed.
No source or original environment change was involved; the earlier error is
retained in the temporary evidence.

After the final Tauri lock and canonical notice update, the rebuilt unsigned
wheel is 1,043,140 bytes, SHA-256
`a79ee0a1fce381e2d08482003affe6065d7249d2dbb7b721970058939a5ca7dd`.
All 440 recorded wheel inputs remained unchanged. Build, fresh hash-locked
installation, pip check, CLI/diagnostics and exact two-tool MCP smoke passed,
including Windows temporary cleanup (exit 0). Independent installed-resource
checks passed for eight modules, eleven providers, the eight-U+2022 mask and
the final 1,424,072-byte notice with component counts 13/57/3/473.

Automatic approval review rejected deletion of the task's ignored verification
caches and empty native resource stub with the generic reason "blocked by policy".
Those paths were retained; no private data, tracked source or Git refs were deleted
as part of that rejected cleanup. A separate OS-temporary metadata cache deletion
was likewise rejected and retained outside the repository.

The actual shipping Ollama image build did not finish locally: its GPU layer
download and build memory demand interfered with source validation. Only
task-created build clients were stopped; Docker Desktop was stopped after
verifying no active containers. Existing images, caches, volumes and user data
were preserved. No model was downloaded or run. Contract/checksum/module evidence
does not stand in for a completed image, smoke test or Trivy scan.

## Protected-PR remediation

PR #112's first actual container job built all three shipping images and passed
the Ollama and frontend runtime smoke tests, backend notice checks, Alpine
lifecycle tests and application-image vulnerability gates. The separate Ollama
scan found six HIGH findings: two Ubuntu OpenSSL/libssl records, one x/net record
and three Go standard-library records. T015 updates the verified Go 1.27.2
multi-platform builder, the coherent nine-module closure including x/net 0.60.0,
and both Ubuntu packages to at least 3.0.13-0ubuntu3.16. The package minimum is
checked during build and smoke and actual versions are recorded in provenance.
Two focused original tests, module verification, YAML, shell syntax and independent
review passed. Actual rebuilt-image smoke/scanning remains a new-head CI gate;
no finding is suppressed and the HIGH/CRITICAL exit policy is unchanged.

The native preflight correctly rejected four Rust/npm Tauri mismatches. T016
aligns Rust core 2.12.4 with npm API/CLI 2.12.1 and exact dialog 2.8.1, fs 2.6.0
and opener 2.7.0. The declared Rust baseline is the tested 1.96 compiler.
Locked metadata, fmt, clippy with warnings denied, 28 tests, licenses and the
scoped vulnerability audit passed. Three upstream generated schemas match across
independent builds; default permission sets, application capabilities and Tauri
configuration remain identical. The commit hook normalized only the generated
JSON files' final newline. The existing glib exception still expires on
2026-10-19. Actual Linux packaging remains a protected CI gate.

Five clean-host Agent Access jobs failed before smoke because their validator
imported packaging before installing host tooling. T017 installs the existing
hash-locked tooling environment first, with an order regression. Clean Python
3.12 and 3.13 hosts independently reproduced the missing-module failure. Python
3.13.14 then completed the full real smoke successfully, including cleanup.
Python 3.12.13 completed pip check, CLI, diagnostics and MCP functional checks but
returned 1 when Windows denied removal of a temporary cryptography DLL after
the bounded retries. No surviving holder or repeated failure was established;
no cleanup policy was relaxed. Two original workflow contract tests and Ruff
passed. The complete cross-platform acceptance matrix must still pass in CI.

GitGuardian classified the original provider E2E literal as Username Password.
Independent account-flow review established it as a synthetic account created
only in the journey's fresh OS-temporary loopback vault. T014 generates a new
cryptographic password per run; real provider E2E and lint passed. No scanner
exclusion or dismissal was added. The final PR #112 scanner still reported only
the original `a906d70` fixture commit; it did not report a new live credential.

PR #112 completed all six mandatory gates and CodeQL. Its six Agent Access
acceptance jobs passed on Linux/macOS/Windows with Python 3.12/3.13, including
cleanup. The rebuilt Ollama image passed the unchanged scan with zero
HIGH/CRITICAL findings. Native Linux preflight, AppImage/deb construction and
both package smokes passed, including deterministic document/backup verification.
The smoke-tested candidate artifact is 12098681419, SHA-256
`d7d493fe8b4a72bf93276898e8e9aca363b022ae46f2610393c909193965c08b`;
this is a CI candidate, not a claim of installer signing or release publication.
Main commit `1a47751d23574fd00d548a69ccc44d31b4dbe608` has a valid GitHub signature
and an exact tree match to the tested PR source. A standard API merge succeeded
after the initial CLI policy rejection, without any policy change or bypass.

During the final ref check, Dependabot created #113 for Tauri API 2.12.2 and
Bootstrap Icons 1.13.2. The inventory guard stopped deletion and retained its
exact tip in a verified bundle. T018 repeats the affected checks and protected
publication with regenerated notices and truthful icon-generator provenance;
its pending gates are not inferred from the completed #112 results.

The first merged main also passed its independent push CI run 39025655766.
The two frontend patches then passed fresh-cache installation and full/production
npm audits with zero findings, 686 unit tests with coverage, lint, build, all eight
browser groups and 57 affected backend distribution contracts. T018 notices
reproduced at 1,424,072 bytes, SHA-256
`e00bf9d3ff6a9233b02e39c1746b3c0a607dcd03bb294bf1638639d7b0f0aebb`.
This is the frontend-only baseline; T019 Python locks require a subsequent
canonical notice and final affected gates. T020 preserves the no-telemetry
boundary before adopting FastAPI's newly instrumented implementation.

T019's reviewed final lock inventories are runtime 58, development 112 and tooling
21 packages, with 121 unique packages in the coherent combined lock closure. All
three hash-required audits passed with zero vulnerabilities, skipped packages or
ignored findings. Common pins, exact Windows pywin32 markers and portable LF
headers were preserved. The final canonical notice reproduces at 1,424,427 bytes,
SHA-256 `7c7e55c2f2444955eae0e5544913dec6ab6d6e5d5028cb20d8317630bf7f1754`,
with component counts 13 frontend / 58 Python / 3 runtime / 473 Rust. Final Node
distribution/license contracts and production build passed with unchanged budgets.

T020's isolated FastAPI 0.143 probe first failed meaningfully: three synthetic
requests (200, 422 and 500) caused 18 ambient provider/setup events. The positive
control verifies tracing, metrics, logs and exporter-configuration probes; public
network access is trapped and no private input values are printed. The explicit
five-control opt-out then passed both privacy tests with zero provider/setup or
egress events. Independent AST comparison confirms this telemetry keyword is the
only production-module semantic change. An initial probe invocation used the
wrong health prefix and failed preparation; it is not counted as the defect's
red reproduction. One upstream Starlette TestClient httpx deprecation warning
is retained. The final complete/static/migration/API/remote follow-up gates remain
pending until actually executed. The final installed Python 3.12.13 environment
matches all 121 packages exactly, with zero missing, additional or mismatched
distributions and a passing pip check. Ruff 0.17.0, mypy 2.4.0 and all applicable
changed-file hooks pass. YAML and frontend-lint hooks skipped because no matching
files changed in this follow-up; the complete T018 frontend lint passed. The
privacy test's formatting was AST-identical. The final Windows backend coverage
run has started on frozen non-Markdown source; its result remains pending.

The final updated-runtime material/provider journeys both passed, including
deterministic document/ZIP downloads, account isolation, revision/consent behavior
and provider-only backup without a profile. Browser forbidden origins were empty;
both temporary vaults and child processes were cleaned successfully. Independent
review found no defect in the vendor-control names, precedence or privacy probes.
Four final performance tests passed in 9.12 seconds with 1,169 unchanged inputs:
profile/page/agenda p95 4.277/42.661/87.233 ms (each budget 200 ms), readiness
p95 21.353 ms and maximum five queries (budget 100 ms/five queries). The final
SQLite upgrade/downgrade/upgrade succeeded with head d0b1c2d3e4f5, integrity OK
and zero foreign-key violations. An initial helper asserted an incorrect table
name after successful migrations; its corrected read-only assertion passed.
The complete Windows run remains pending. A subsequent documentation-only commit
corrects a stale virtualenv version reference and records these finished checks;
its required PR gates must run on that final head. No non-Markdown input changed.

That Windows run subsequently exposed a time-dependent test fixture in provider
commit-identity verification. It was interrupted at 48%, exit 1, without a pytest
completion summary; the 1,169-input guard remained unchanged. It is not a pass.
The positive fixture edited the original provider, which invokes SQLite's
automatic updated_at and is not the state of a real archive restore. Production
correctly rejected the resulting timestamp mismatch. T021 changes only the test:
delete/flush/insert the complete decoded archived row, including both timestamps,
as the real restore does. Exact production verification is unchanged. Each new
timestamp negative changes only one expected field, avoiding clock dependence.

The original fixture failed deterministically with a distinct SQLite update clock
(one failure in 1.90 seconds; updated_at was the sole content mismatch). The final
two timestamp cases pass in 2.27 seconds; all 19 provider-only tests pass in 19.40
seconds, including real API restore and before/after-commit failure handling.
Ruff and applicable hooks pass. Mypy/frontend hooks skip this test-only change;
the prior complete static/frontend checks remain recorded separately. Other test
function ASTs are identical after required Ruff formatting. A new frozen Windows
coverage run and new-head protected CI must finish before final publication.
The coordinator's first hook invocation selected system Python 3.14, which lacks
Ruff, and returned 1. Repeating with the final locked Python environment first
on PATH passed every applicable hook; YAML, mypy and frontend hooks had no
matching changed files. No hook rewrote source in either invocation.

Prior head 5459711 passed Linux backend CI (2,949 passed, 11 skipped, 666.53 seconds,
83.59% combined coverage), all four performance gates, frontend, Rust, containers,
release supply-chain, CodeQL and six Agent Access acceptance environments. The
unsigned wheel candidate is 1,042,558 bytes, SHA-256
`9ee94376d44d27ffdeeedc8e60f31c00468637d106103653ebad3162c51bfaa2`.
Its notice/lock checksums match the manifest. Rust fmt/clippy pass, all 28 Rust
tests pass, and license/audit checks retain only the disclosed existing Linux
exception and unmaintained warning. These executions are tied to that prior head;
they do not claim the post-T021 protected gates have already run.

Native installer clean-install/restart/upgrade across supported systems, signing,
release artifact checksum/SBOM/provenance and applicable model/hardware evaluation
remain release qualification obligations. None is claimed from source suites or
the unsigned wheel proof. PR #112's protected checks and signed-main content
verification passed; the automated follow-up must repeat protected publication.

## Verified integration baseline and post-integration follow-up

The earlier pre-publication snapshot is now complete. PR #115 merged through the
standard protected API to signed main 1b897f0a1a9fc734a6949859603a0c2c4ceb095a;
its tree 70b9702cdf804d3817318e5827fcf9fdaea41179 exactly matches tested source
999f383. Main was the sole local and remote branch, with a clean worktree and no
open PR or stash. Eight complete Git bundles pass verification; the final bundle
SHA-256 is cee7a3ce89c779ae8c9bb511e0d7f4d3bbff4d39e7f937a58519589a8e98f8c0.
The durable local evidence is under .git/careeros-recovery/2026-10-17, with public
execution evidence in PR #115 and the associated workflows.

Frozen Windows verification completed: 2,944 passed/17 skipped, 1,233.74 seconds,
82.03% combined coverage with branches, pytest/wrapper exit 0 and no changes to
1,169 inputs. Four performance skips passed separately; thirteen skips are POSIX
contracts inapplicable on Windows. Actual main Linux verification completed:
2,950 passed/11 skipped, 686.29 seconds, 83.59% combined coverage; four performance
tests passed in 5.65 seconds. Main CI 39030464877 passed all eight jobs and main
CodeQL 39030464781 passed all four languages. Frontend 686 tests, Rust 28 tests,
six Agent Access environments and both native package smokes passed. The wheel
and native candidates are unsigned; no release was published. The existing glib
exception and its 2026-10-19 expiry were not extended.

Some ignored caches/generated directories and a task-owned OS npm metadata cache
remain because automatic approval review rejected their deletion with the exact
reason "blocked by policy". No bypass was attempted. T011 records this disclosed
cleanup exception rather than claiming that every generated file was removed.

The owner then requested continued refactoring and anomaly correction. T022–T026
track new work on a dedicated codex branch; the baseline's passing results do not
substitute for affected follow-up checks. Four bounded defects were reproduced:

- Actual Uvicorn handlers can bypass root-only private logging, and cached
  exception text can bypass the current privacy formatter. The first probe
  reported an unattested 0.49.0 environment and is not authoritative. The probe
  was repeated with exact environment B, Uvicorn metadata/module 0.54.0 matching
  the hash lock and official wheel; all three leak cases were reproduced without
  printing private sentinels. Four authoritative regression cases failed before
  correction. An initial capture attempt mixed two real cache failures with two
  stdout-capture harness failures and is not counted as four valid red cases.
  A stronger real Config trace probe then reproduced two additional failures
  with opaque URL/query/private preformatted server messages. The final policy
  retains constant server/ASGI events and only allowlisted HTTP method/integer
  status metadata; sealed events remain idempotent across two handlers. All ten
  final regressions pass in 14.399 seconds, including real MessageLoggerMiddleware,
  both startup orders, cached exception text, structured diagnostics and stdio
  preservation. Independent review finds no material issue.
- Malformed deflate, LZMA and UTF-8 ZIP metadata escape the archive validation
  boundary. A real synthetic API restore returned 500 and remained pending;
  parser/API regression tests reproduced all nine cases before the fix. They all
  pass after precise decoder exception normalization, with bounded 422 responses,
  unchanged records/session and ready lifecycle. All 222 portability tests pass
  in 190.69 seconds; ten guarded inputs are unchanged. Independent review passes.
- Provider writes succeed but the following failed catalog read discards their
  acknowledged state. Real hook regressions reproduced five failures before the
  change. Extended import regressions reproduced two lost-count cases and then
  two missing-row cases before the correction. Only actual redacted provider
  rows returned by the server are added to the catalog. The final focused suite
  passes 38 tests in six files, including pending UI single-flight controls,
  actual write errors and stale/unmount handling. Independent review passes.
- Reusing a photo trusts metadata without checking stored bytes or normalized
  status. Six regressions failed meaningfully before the guard, including actual
  API 201 instead of 422; a healthy duplicate control passed. After the contained
  read guard, all seven pass in 4.64 seconds and 23 photo/concurrency/resume API
  tests pass in 16.37 seconds. Rejection leaves selection/revision unchanged,
  releases the transaction and does not overwrite missing/corrupt bytes.

Follow-up full frontend verification passes: 698 tests in 105 files, coverage
82.36% statements / 73.07% branches / 74.26% functions / 87.11% lines; lint,
Node/license/distribution/icon contracts and production build pass. Build byte
budgets and the canonical notice remain unchanged. All 430 guarded inputs are
unchanged. The standard npm coverage command initially wrote ignored reports
under frontend/coverage; these generated reports were subsequently moved intact
to its OS-temporary evidence directory after explicit path/ignore/containment
checks. No report bytes were discarded and the source directory is absent.

All applicable changed-file hooks pass with exact Python B first on PATH:
whitespace, EOF, conflict/size/debug checks, Ruff over backend/tests/scripts,
Ruff format, mypy over backend/scripts and frontend lint. YAML skips because
there is no matching YAML change. No source rewrite occurred. T022's earlier
mypy invocation on only core/logging.py and main.py reported three attr-defined
errors resolving the existing configuration.packs module; the ordinary complete
backend/scripts invocation passes. The subset result is retained as an actual
failed command rather than described as a successful gate.

All eight browser/API groups pass on exact Python B and Node 24.18.1 in 126.131
seconds, without rebuild or dependency installation. Both real API journeys pass,
with zero remaining synthetic vaults. Rust fmt/clippy/test also pass on 1.96.0
using the existing OS-temporary target cache, locked/offline: 28 tests pass.
The parallel Tauri build removed only the final LF from three generated tracked
JSON schemas. Both wrappers correctly reported source-guard failure despite
passing test commands; neither wrapper is represented as an initial clean pass.
For each schema, SHA-256 of the generated bytes plus one LF equals its exact
pre-run hash. After checking both hashes, the coordinator restored only that LF;
all three files again match the original bytes and Git has no schema diff.
The original guard failure and the canonical-restoration proof are retained.
No JSON meaning, permission, capability, dependency or production input changed.
The complete browser guard reconciles all 1,213 source/dist entries with zero
final differences; the transient teardown process also exited normally. No Rust
or browser gate was repeated after proving byte-identical canonical restoration.

The fresh SQLite migration roundtrip also passes on exact Python B:
upgrade to d0b1c2d3e4f5, downgrade to c0a1b2c3d4e5, then upgrade to head; every
command exits 0. Integrity is OK and foreign-key violations are zero after each
phase. The actual table sets match ORM metadata plus alembic_version, with the
provider table present/absent/present. All 1,173 guarded inputs match both the
migration run's initial manifest and the frozen backend baseline. Total duration
is 9.457 seconds; all data and evidence are in the operating-system Temp directory.

Final combined Windows backend verification passes: 2,965 passed, 17 skipped,
1,265.69 seconds and 82.055818% combined coverage with branches (82.06% rounded,
minimum 80%). JUnit records 2,982 cases, zero failures and zero errors; pytest
and wrapper both exit 0. The complete 1,173-input start/end guard has zero
differences. Thirteen skips are POSIX-only filesystem/locking contracts; four
are opt-in performance cases and all pass in the separately enabled run.

The four performance tests pass in 9.05 seconds, with zero input differences and
pytest/wrapper exit 0. Readiness p95 is 15.611 ms with at most five queries
(budgets 100 ms/five queries). Profile/page/agenda p95 with 10,000 records is
4.420/43.153/87.007 ms (each budget 200 ms). Deterministic generation and detailed
resume reads pass their 500/200 ms budgets; those two tests do not print measured
latencies. Values are from this execution, not copied from the prior baseline.

All four changes have independent review without material findings; the final
artifact review confirms twelve FR, ten SC, five outcomes, nine plan decisions,
eight constitution principles and twenty-six tasks with no additional unbuilt
requirement. T022–T026 are complete. This is a pre-publication source snapshot:
the new protected PR checks, signed-main exact-tree proof and branch cleanup are
recorded in PR metadata and durable private Git recovery evidence after actual
execution. No future CI result, signing qualification or release is claimed here.
