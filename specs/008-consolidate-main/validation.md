# Validation evidence: Consolidate all work into main

Date: 2026-10-20. Current branch: `codex/quality-followup`.
Status: signed PR #119 main dee0e5e is the verified baseline. Current quality,
UI, dependency and formatting work has its own evidence below. The expired
glib exception blocks integration and recovery-backed ref cleanup. Actual
current-head protected outcomes belong in PR metadata and the private recovery
ledger; earlier successful gates are not substituted for them.
No production release or installer signing claim. Earlier sections retain the
actual historical executions; current-cycle evidence appears at the end.
A pending entry is never presented as a passing check.

Historical initial branch: `codex/production-readiness-refactor`; first follow-up:
`codex/final-dependency-patches`. PR #112 and subsequent cycles through PR #117
were merged and verified before the current extended refactor.

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

## Verified UI baseline and continued refactor

The preceding source snapshot is integrated through PR #116 as signed main
cdc91c10e9dcc49ed77e238f1556d34692d2e0ca, parent 1b897f0, with valid GitHub
signature and tree 0a2f4be8ef239e3b50fb0c13a8cf3be5755139f4 exactly matching
reviewed source d79604f. All six required PR gates passed; the full inventory was
23 SUCCESS and two intentionally skipped release-publication jobs. All six Agent
Access environments and both Linux native package smokes passed. Main's own CI
39036469180 completed eight jobs successfully and CodeQL 39036469070 all four.
Main Linux: 2,971 passed/11 skipped, 692.02 seconds, 83.63% combined coverage;
four performance tests passed in 5.51 seconds. Both new bundles verify with full
history, main was the only branch, and the final independent audit found no
dirty worktree, stash, open PR or source-tree mismatch. Final private evidence
is retained in .git/careeros-recovery/2026-10-17; the public PR includes checksum
and unsigned-candidate details. No release or tag was published.

The owner then requested UI refactoring. T027–T032 track that separate cycle.
Read-only synthetic probes reproduced coach stale-selection/new-draft loss,
application selection stolen by a late acknowledgement, jobs filter/count/undo
corruption, and modal background/stack cleanup failures. Explicit renderer logs
and installed React production default error callbacks also forward raw errors;
the UI privacy change includes both channels. These baseline results never imply
that a new UI implementation or future gate has passed. All new probes and
execution artifacts remain in OS Temp, without reading personal vaults.

### UI defect reproduction and focused verification

T027's actual production React probe reproduced both the workspace boundary and
default root callback leaking synthetic private error content (exit 1, fallback
visible, source unchanged). With the extracted boolean-only boundary and all
three explicit root callbacks, the same production runtime reports only the
fixed caught/uncaught/recoverable codes; private content is absent and the
translated fallback remains visible (exit 0, source unchanged). The focused
suite passes 47 tests in nine files, 7.83 seconds. The later auth/entry/boundary
subset passes 36 tests in four files, 3.88 seconds. The real ESLint API contract
first failed for an unsafe virtual console call, then passes all four Node
distribution tests after production no-console enforcement; the actual reporter
is the only exemption. Scoped lint passes for all sixteen owned frontend files.
The initial optional Babel-plugin failure, unsupported Vitest --cacheDir command
(zero tests), old unsafe JobTable expectation (46 pass/one fail), and a classic-
versus-automatic JSX probe mismatch are retained as failed harness/intermediate
commands, never counted as successful gates. No dependency was installed.

T028 first reproduced stale conversation selection and loss of a newly typed
composer draft. Its regression run failed eight tests with two controls passing.
The final controller/service/view suite passes 17 tests in three files, 6.99
seconds, with lint and unchanged-input checks passing. The rendering view is 47
lines and controller 196; independent review finds no material issue.

T030/T031 initially fail seven regressions with 24 passing controls. Expanded
independent review found three more pending-detail/creation-selection defects,
then a fourth close/reopen form-session defect; each was reproduced before its
correction. The final combined suite passes all 43 application/jobs tests in
22.60 seconds. Lint passes for all seven owned files; the extracted application
view and card JSX are AST-equivalent to the original presentation. Both areas
have independent review without material findings. The existing React act
warning in the deep-link agenda test was also present before these changes and
was not suppressed. All evidence remains in OS Temp.

T029's actual dialog probe first passes one control and fails three isolation,
Escape and scroll-ownership cases. The shared stack passes those probes and 51
tests across seven affected suites, including thirteen new lifecycle cases.
Native Chromium then passes sixteen behavior checks at each of 320/390/1440
pixels, with zero page errors or external requests. Nine axe runs report zero
violations; two dialogs retain a manual color-contrast incomplete per width.
The appearance comparison finds a real inherited glass-panel color/shadow
change after moving ConfirmationDialog to a body portal. The final narrow CSS
correction, visual review and source freeze remain pending; these measurements
are not represented as a complete final UI gate.

That appearance finding is now corrected by adding only the confirmation-portal
selector to the existing glass-panel rule, with all declarations unchanged.
After transitions settle, computed styles and bounds match exactly at all three
widths; zero overflow, page errors or external requests occur. The focused probe
uses baseline built CSS plus that production rule read verbatim; it does not
substitute for the subsequent full production build. Axe reports zero violations
and retains one manual contrast incomplete per viewport. Independent visual
inspection of the final 320/1440 screenshots and two code reviews pass.

The analysis-dialog shell is now 112 lines, evidence view 52 and section module
95, with each section component below 40 lines. Eight actual rendered-DOM
comparisons pass for empty, unverified, validated-local, attested/unattested/
wrong-provenance external, malformed-array and sparse cases. No validation
predicate or publication authority moved into the presentation components.
The final seven affected modal suites pass 55 tests in 41.601 seconds; ESLint
passes for eleven JavaScript files, diff checks pass for all twelve owned inputs,
and source hashes are unchanged. The final source freeze was announced before
starting the combined frontend and five affected Python contract gates.

The five affected Python contract files pass on exact Python B: 78 passed,
zero skipped, 29.63 seconds, pytest and wrapper exit 0. Repository hygiene,
distribution configuration, frontend security exceptions, product identity and
release workflow contracts run with DATA_DIR set to a fresh OS-temporary path
before the first backend import. All 1,189 non-Markdown inputs match before/after.
Backend/native/schema/dependency production inputs remain byte-identical to
signed main cdc91c1. No complete local backend, Rust or migration run is claimed
for this UI-only cycle; their exact baseline results above are retained, with
fresh protected remote checks still mandatory for the new head.

### First aggregate UI run and measured bundle failure

The first aggregate frontend run passes 756 tests in 111 files, 90.25 seconds.
Coverage: 84.01% statements (5,872/6,989), 74.63% branches (4,502/6,032),
75.82% functions (1,581/2,085), 88.77% lines (5,202/5,860). All thresholds are
unchanged. Node preflight and four runtime tests, eleven license/distribution/
icon contracts, icon verification and lint pass. Vite compilation also exits 0.
The separate mandatory bundle gate exits 1: AuthenticatedWorkspace is 32,085
bytes, exceeding its unchanged 32,000-byte limit by 85. Thus the equivalent
production build gate is FAILED; browser/API groups were not started.
All 1,189 source inputs remain unchanged during this run and no repository
coverage directory exists. The failed build's forty-asset hash manifest and
all original logs/results remain in OS Temp without overwrite.

The first corrective implementation change was a narrowly reviewed deduplication
in modalStack: equivalent Tab edge/fallback branches, visibility selectors and
attribute restoration. No focus lifecycle, ownership, state restoration or
budget is weakened. The earlier 78 Python contracts attest the preceding source
snapshot; they do not establish a successful bundle. Renewed modal/native and
full frontend/build checks on the final source are still required. Backend,
native and dependency inputs remain unchanged.

The second aggregate run also passes all 756 tests in 111 files, 93.23 seconds,
plus Node/license/icon contracts, lint and Vite compilation. Coverage for that
snapshot is 83.99% statements (5,863/6,980), 74.59% branches (4,492/6,022),
75.83% functions (1,582/2,086), 88.75% lines (5,195/5,853). The raw workspace
chunk now passes at 31,943/32,000 bytes, but the gzip gate fails at 9,651/9,600
bytes. This aggregate is also FAILED, with zero source-guard differences and
no E2E run. Its logs and forty-asset manifest are preserved separately.
The renewed modal checks pass 55 tests in 42.017 seconds and 48 native behavior
assertions across three widths; visual comparison has zero differences, and
nine axe runs have zero violations with six retained manual-contrast incompletes.

Actual import-graph review then finds the route-specific analysis gate pulling
ModelManager into the eager workspace shell. A one-file correction loads the
unchanged RequiredLocalAnalysis through the existing module-level React lazy
route pattern, Suspense fallback and error boundary. Its readiness/consent code,
model manager and synchronous modal lifecycle remain unchanged. Independent
review passes. Manual deep links can now avoid the analysis/setup implementation.

The subsequent actual production build and unchanged budget validator PASS:
workspace JavaScript 17,130 raw / 5,775 gzip; entry 267,104 / 82,974; largest
locale (Italian) 89,925 / 28,401; lifecycle CSS 21,837 / 5,841; initial resources
379,913 / 117,780; workspace CSS 434,350 / 72,155 bytes. All three build-wrapper
commands exit 0 and all 1,189 source hashes remain unchanged. The complete
frontend quality run, actual route-loading probe and eight browser/API groups
on this final source are pending; the successful build is reused without a
redundant rebuild, with source/distribution guards.

### Final frozen UI quality and route-loading evidence

The final quality wrapper passes all five commands: Node preflight, four runtime
contracts, complete V8 coverage, eleven license/distribution/icon contracts and
lint. All 756 tests in 111 files pass; the coverage command takes 93.214 seconds.
Final coverage is 83.99% statements (5,863/6,980), 74.60% branches (4,493/6,022),
75.83% functions (1,582/2,086), 88.75% lines (5,195/5,853), with unchanged
thresholds. The successful actual build above is reused on byte-identical source;
all 1,189 source inputs and 44 distribution files remain unchanged (1,233 guarded
entries). Coverage/config/cache are entirely in OS Temp; frontend/coverage is absent.

A separate actual-build browser probe passes seventeen assertions in two fresh
contexts. Direct /jobs loads JobsPage and its shared modal code without requesting
RequiredLocalAnalysis or ModelManager. Direct /coach requests both feature chunks
and renders the real locked setup UI; no composer/unlocked analysis, readiness
inference or model mutation occurs. The only POST is synthetic authentication
refresh. There are zero external requests, page errors, HTTP failures or
unexpected API calls. All source/dist bytes and the immutable OS-temporary build
copy match; independent inspection of both screenshots passes. This two-route
graph smoke does not substitute for the eight browser/API groups still running.

Independent cross-manifest review compares the earlier 78-contract snapshot with
the final source: only modalStack.js and the one workspace import declaration
differ; all other 1,187 inputs match. Reversing that eager-to-lazy declaration in
memory exactly reproduces the earlier workspace hash. Backend, native, dependency,
configuration and RequiredLocalAnalysis module bytes remain unchanged. No Python
contract rerun or unexecuted backend/native check is claimed for the final UI
deduplication/loading changes.

All eight browser/API groups now pass on the final built source: npm exit 0,
138.513 seconds, Node 24.18.1 and exact Python B 3.12.13. This includes the
responsive portfolio, agenda/DST/contrast, login, Agent Access, Agent Work,
actual materials API, actual providers API and responsive workspace shell.
All 1,233 source/dist inputs remain unchanged and no synthetic vault remains.
The wrapper initially exits 1 because its immediate descendant-process snapshot
contains PID 20448. Its original result is preserved, not changed into a pass.
At the first subsequent read-only lookup that PID is absent; the final process
and TCP check at 15:04:46 UTC finds zero owned processes/endpoints and zero
vaults. The final 1,233-input rehash also has zero differences. No process was
killed and no test or build was repeated. The wrapper recorded only historical
descendant IDs, so the departed process's name/start/parent cannot be recovered
and are not invented. The actual tests pass and teardown is reconciled; the
initial resource-guard failure remains part of the execution history.

All applicable changed-file hooks pass on exact Python B in 63.345 seconds:
trailing whitespace, EOF, conflict/size checks, global Ruff over backend/tests/
scripts, global mypy over backend/scripts and frontend lint. YAML, Python debug
statements and Ruff formatting skip because no matching files changed. All
1,346 guarded repository inputs, including Markdown, remain byte-identical
through the hook run. Final evidence/checkbox edits only affect the six active
Markdown artifacts; their final text checks are recorded separately.

Independent implementation, source-graph and artifact reviews find no unresolved
material issue or additional task: 17 FR, 15 SC, six outcomes, ten plan decisions,
eight constitution principles and 32 mapped tasks. T027–T032 are complete as
verified source and integration hand-off. The new head's protected PR checks,
signed-main exact tree, verified recovery bundle and final branch inventory
remain mandatory actual execution in the PR/private recovery ledger. This
pre-publication source snapshot claims no future CI, merge, signature or release.

## Extended refactor baseline and reproduced findings

The preceding UI cycle completed through PR #117. Signed main cc8c9dd and
reviewed source 4f0c55b have tree e679b3a. Post-merge CI 39045287407 passed all
eight jobs and CodeQL 39045287387 all four. The verified complete recovery
bundles, signature/tree proof and sole-main clean ref inventory are retained in
the private Git recovery ledger. No new release/tag was published.

The new owner request starts from that clean main on
codex/extended-refactor-cleanup. Constitution 2.0.1 is reviewed unchanged;
specification, plan and tasks precede implementation. Independent initial
inventory finds 1,346 tracked files and no tracked temporary/build/cache/log
candidate. Development infrastructure and policy-blocked caches remain intact.

Actual component probes reproduce three UI defects (three failing regressions,
three passing controls): dirty profile internal navigation bypasses its
unload-only guard; acknowledged resume deletion followed by failed catalog read
keeps the deleted selection; acknowledged claim confirmation followed by failed
profile read keeps the old draft revision. A separate proposed save-during-edit
race is rejected after inspection: the actual profile fieldset is disabled while
saving; no implementation change is justified by that hypothesis.

The actual source-import router with isolated SQLite/files reproduces false
successful duplicate reuse for missing bytes, same-length corruption and wrong
stored byte_size. The healthy control is idempotent. Rejected-state probes leave
one asset/source and both synthetic accounts' profile revisions unchanged. The
first harness attempt returned 404 from an incorrect synthetic route prefix;
the corrected real-router probe passes and no source was changed during audit.

The initial Rust run passes fmt, Clippy with warnings denied and 28 tests, but
the wrapper correctly exits 1: its 70-input guard detects six before/after entries
for three generated schema files. Independent byte comparison proves each change
is exclusively removal of the final LF; parsed JSON is identical. T038 adopts
the generator bytes and exempts exactly these paths from end-of-file-fixer.
A second actual native run passes all three commands with zero changed inputs
(fmt 0.401 s, Clippy 0.968 s, test command 2.478 s; 28 tests). The focused EOF
hook explicitly skips those generated files; independent post-hook hashes and
JSON comparisons remain identical. The original guard failure is retained.

Implementation review, final aggregate checks, analysis/convergence and this
cycle's protected integration/ref cleanup are pending. Prior checks are not
substituted for unexecuted changed-source gates.

### Extended implementation and independent verification

T033 is frozen at a 124-line compatibility facade and fourteen internal modules
(largest 256 lines). All 291 existing focused evidence/policy/attestation/search
tests pass with no skips. Ruff, changed-file formatting and scoped mypy pass.
Independent comparison verifies 42 function/class ASTs: 39 exact, three differing
only by explicit catalog-configuration arguments. All 25 moved assignments,
three vocabulary set literals, 1,077 literal occurrences/622 typed values and
the composed 429-word vocabulary are identical; imports form an acyclic graph.
The implementation owner's 540 ordered-output comparisons pass. A separate
coordinator corpus verifies 384 complete candidate/job pairs across 96 synthetic
cases and four public version/description-limit combinations, including ordered
serialization, complete metadata, bindings and all fingerprint APIs. Both
comparison passes preserve the public dynamic configuration behavior.

T037's actual API regression starts with 15 failures/three passing controls and
passes all eighteen cases after the fix. The complete focused source/API/
concurrency/publication/recovery/parsing set passes 69 tests with zero skips in
46.51 seconds. Source facade 255 lines, integrity helper 90; the remaining
publication/commit-recovery function bodies are unchanged. All three changed
files are LF. Independent review verifies ownership from either relationship,
bounded errors, canonical contained reads and fail-closed storage validation.

T035/T036 pass 77 focused tests in six files (25.01 seconds), changed-file lint
and a final canonical-LF ten-test UI run. Earlier focused invocations are retained:
72 passed/one failed due to an incorrect fixture revision expectation; 75 passed/
two failed due to an incorrect translated button label and incomplete mock cleanup.
Those were test-only corrections. The final thirteen-file freeze and independent
review match exactly. The profile hook is 40 lines; the acknowledgement hook 106;
the resume controller shrinks from 319 to 284. Real routed DOM, API-client 503,
write-failure, read-only retry, newer-draft/selection and forced-locking cases pass.

The first complete frontend snapshot passes 774 tests/112 files and all unchanged
coverage thresholds: 84.18% statements (5,931/7,045), 74.88% branches (4,541/6,064),
76.14% functions (1,599/2,100), 88.91% lines (5,253/5,908). Four runtime and eleven
license/distribution contracts, 128 workspace/nine lifecycle icons and global lint
pass. Production build and unchanged budgets pass: entry 267,104 raw/82,973 gzip;
Italian locale 89,988/28,424; lifecycle CSS 21,837/5,841; initial 379,976/117,802;
workspace CSS 434,350/72,155; shell 17,130/5,782. All 1,208 source inputs and
44 built assets remain unchanged through those runs; all 1,365 inputs, including
Markdown, remain unchanged through the applicable full changed-file hooks.

Global Ruff over backend/tests/scripts and mypy over backend/scripts pass with
zero input changes. Fresh Alembic upgrade/head, downgrade/one and upgrade/head
passes at d0b1c2d3e4f5 with SQLite integrity `ok` and zero foreign-key violations.
Four separately enabled performance cases pass: readiness p95 26.231 ms against
100 ms, at most five queries; profile 5.912 ms, application page 62.009 ms and
agenda 133.149 ms against 200 ms. The independent desktop Python suite passes
32 tests with six skips: five POSIX-only ownership/no-follow contracts and one
artifact-only packaged-lifecycle smoke requiring CAREEROS_SIDECAR_BINARY.
Its first run had 31 passes/one failure/six skips because the OS-temporary
launcher lacked a multiprocessing main guard. The guarded launcher passes; no
application or repository test was changed for that harness error.

An offline real wheel build from 398 authorized snapshot inputs passes without
network, dependency installation or repository build/egg-info output. The wheel
is 1,053,052 bytes, SHA256
`fd65730c365880b493efb6a936103ac39822bafc286d286ccf68194914e2c2d9`.
All fourteen catalog modules and the facade, packaged Python/data/license inputs
and entry points match source bytes. Isolated imports and eight complete
synthetic/fingerprint comparisons from the byte-verified extracted wheel pass
with zero network attempts and zero differences across 402 guarded inputs.
The preceding direct ZIP-on-sys.path import attempt fails on the historical
backend.core namespace directory layout; it is retained as unsupported, not a
passing check. Ordinary extracted-wheel layout passes. This unsigned pure-Python
source wheel is verification evidence, not a published native installer/release.

All eight browser/API groups pass on the first built snapshot (npm exit 0,
137.037 seconds); zero vaults and all 1,252 guarded source/dist inputs remain
unchanged. The wrapper returns nonzero for descendant 14544. Captured identity
is conhost.exe, parent 3204, created before npm; that parent's historical identity
was not recorded, so ownership by the wrapper remains probable, not established.
Independent later review finds that PID absent, zero task processes/listeners/
vaults and unchanged source/dist. No kill or rerun is used for reconciliation;
the original nonzero wrapper is preserved.

Real-build browser review verifies ten cases/103 assertions: profile EN/IT at
390/1,440 px (native deny/accept/save), and resume EN/IT at 320/390/1,440 px
(acknowledged deletion, one expected GET 503, readable warning and GET-only retry).
There are zero page errors, egress, unexpected API calls or writes, and browser/
server cleanup and source/dist/owned-file guards pass. Four temporary-helper
failures are retained separately: snapshot destination already existed before
exclusive copy; missing asynchronous dialog wait; off-canvas menu visibility
misclassification; and the wrong English CV button label after all four profile
cases had already passed. Only the remaining six CV cases continue, exit 0;
no successful profile case is repeated or earlier exit reclassified as passing.

Independent screenshot inspection then discovers a real product defect: the
template selector references two missing feature-local message keys in both
languages. software-en is canonical/default in the real nine-preset catalog;
messages are statically loaded, so this is not a harness or lazy-loading issue.
T039 records the requirement before adding exactly four translations and a real
four-case selected/empty EN/IT selector test: four RED before, four GREEN after.
Only templateMessages.js and the new ResumeSettings.test.jsx change; independent
manifest review proves the other 1,207 original inputs, including all 630 backend/
backend-test files and all native/configuration/dependency inputs, are unchanged.
Fresh final frontend coverage/lint/build/browser runs cover this delta below.

The first complete backend attempt is interrupted with exit -1 after failure/
error markers beyond the printed 19% progress, with no completed summary or pass
claim. Its temporary launcher retained DATA_DIR in the environment, causing
Alembic fixtures with independent configured roots to be correctly rejected.
The first such setup error is independently reproduced; unsetting DATA_DIR only
after initial isolated settings configuration makes the same seven targeted
tests pass in 24.77 seconds. No containment rule or repository test changes.
The complete run restarts with that corrected, main-guarded launcher. It began
before the two-file T039 UI fix: its strict global input guard must retain those
known differences, while backend input identity is independently attested. Its
actual aggregate result and final UI evidence are recorded below; protected
integration still requires its own subsequent execution.

### Final frontend snapshot after the selector correction

The final complete run passes 778 tests/113 files with unchanged thresholds:
84.18% statements (5,931/7,045), 74.85% branches (4,539/6,064), 76.14% functions
(1,599/2,100), 88.91% lines (5,253/5,908). Runtime, license/distribution/icon and
global lint checks all pass. All 1,253 guarded source/dist inputs remain unchanged.
The actual production build passes unchanged budgets: entry 267,104/82,973,
Italian locale 89,988/28,424, lifecycle CSS 21,837/5,841, initial resources
379,976/117,801, workspace CSS 434,350/72,155 and workspace shell 17,130/5,778
bytes (raw/gzip). Build guards cover 1,209 source inputs and 44 output assets,
with zero differences.

Two fresh label/warning captures on that final build pass 31 assertions, EN at
320 px and IT at 1,440 px. Both exact translated template labels appear, neither
raw message key appears and controls/warning fit without overflow. There are
zero page errors, external requests, unexpected APIs or writes. All fifteen
owned UI inputs, 1,209 source files and 44 snapshot/dist assets remain unchanged;
browser and server close. The preceding ten cases and helper-failure history are
retained rather than repeated or relabeled.

All eight E2E groups pass again on this final changed build: npm and outer caller
both exit 0, 132.649 seconds, zero test descendants/vaults and zero differences
across 1,253 inputs. The OS-only wrapper now records its own PID/creation time
and npm start; it classifies only an identified conhost.exe direct child created
between wrapper creation and npm start as the runner's console. Missing identity/
timestamps and all other descendants still fail closed; no subtree is excluded.
The recorded runner console 20220 and wrapper 18128 are independently absent by
identity after exit, with zero attributable processes/listeners/vaults. All
1,253 input and final build hashes match. No process is killed. The first
wrapper's nonzero result and unknown historical parent identity remain intact.
An initial read-only review helper timestamp cast error is corrected only in
Temp; its actual final verification exits 0 and both executions are retained.

### Final complete backend and source hand-off

The corrected Windows Python 3.12.13 run passes 2,983 tests with 17 skips in
1,752.71 seconds; pytest returns 0 and combined branch-aware coverage is 82.12%
against the unchanged 80% gate. Thirteen skips are POSIX-only owner/mode,
no-follow, ctime, FIFO and fcntl contracts. The other four opt-in performance
cases pass in the separately enabled run recorded above.

The strict global launcher returns 1, not a passing wrapper result: its 1,208-input
baseline differs by exactly the T039 templateMessages.js change and newly added
ResumeSettings.test.jsx. All other 1,207 original inputs, including all 630
backend/backend-test inputs and static/native/configuration/dependency inputs,
are identical. Independent final manifest review attests this scope; completed
final frontend/build/browser/E2E gates cover both UI changes on the 1,209-input
snapshot. The original guard and earlier interrupted run remain unchanged.

T039 and every implementation task are complete and independently reviewed.
T034 attests completed source verification, artifact reconciliation and the frozen
protected-integration hand-off. New PR checks, actual signed-main exact-tree
verification, verified recovery bundles and final ref cleanup are recorded after
execution in PR metadata and the durable private Git recovery ledger. This
source record does not pre-approve those steps or a production release.

## State-consistency follow-up baseline and reproduction

PR #118 subsequently completed protected integration: source 9f99546 and signed
main 06fe0e0 share tree a05899b. Main CI passed eight jobs and CodeQL four; local
and remote inventories contained only main with no open PRs and a clean worktree.
The new codex/state-consistency-refactor cycle begins from that verified state.
Constitution 2.0.1 remains unchanged; no dependency, schema or authority changes
are required. All new reproduction/output data is synthetic and stays in OS Temp.

The initial real-component UI audit has two failures and two passing controls:
a late search-start acknowledgement redirects after navigation away, and a
cancelled agent-work card remains in Queued. The real restart-service audit has
one failure and one passing control: two concurrent starts create two synthetic
children, but final stop reaps only the tracked one. A real isolated SQLite
search-release reproduction retains a replacement lock but incorrectly erases
its reserved status; the valid-owner release control passes.

Separate cached SQLite sessions reproduce accepted stale claim promotion with
unchanged revision numbers and loss of the first claim link. HTTP reproduction
also finds empty optional subtitle returns 422 after committing a fact, profile
and draft revision; retry conflicts. A nonempty-subtitle control returns 200.
These are source defects, not expected user-visible behavior.

The first local search test invocation exits 4 because its requested API test
path does not exist; zero tests ran. The corrected run passes 168 tests but the
strict wrapper exits 1 because the new regression test changed during execution.
The subsequent frozen scoped run passes 169 tests in 36.93 seconds, command and
wrapper both exit 0, with six owned source/test inputs unchanged. Its coverage
includes status/repository, API, scheduler, pipeline and service failure paths.

Native fmt, clippy with warnings denied and cargo test pass on 70 unchanged native
inputs. Full final source gates, independent review and protected integration are
still pending and are not represented by these proportional results.

T043 independent review finds no material issue: token-conditional lock release
and JSON reservation ownership protect the same SQLite transaction, only reserved
status is cleared, and rollback and local newer-owner cases are covered. The
original real-SQLite reproduction now passes with the replacement lock and full
status preserved. A formatting check initially reports the new test file needs
formatting; it is corrected and both focused Ruff checks pass. This final
whitespace-only change will be included in the complete frozen backend run.

T045 regression-first execution has five failures and three passing controls on
the prior source. The corrected promotion uses the existing serialized SQLite
write/current-owned-draft pattern, omits empty legacy subtitle overrides and
validates the complete response before commit. The final focused run passes 33
tests in 25.73 seconds with zero skips, including whitespace subtitles, cached
same/different drafts, concurrent winner/conflict, response/commit rollback and
foreign ownership. Scoped Ruff, formatting and mypy pass. Independent source
review confirms current revisions are read after acquiring the SQLite write
lock, response validation precedes commit, and explicit confirmation authority
is unchanged. No schema or API shape changes are introduced.

T042 adds a 73-line startup-ownership/termination helper and keeps the managed
runtime's existing verification/environment/argv/restart-limit contracts. The
regression-first run records ten failures and five passing controls on the prior
lifecycle. The corrected proportional suite passes 159 tests with zero skips in
8.74 seconds, including fifteen new ownership cases, inference/service/API and
lifespan/shutdown boundaries. Ruff, formatting and scoped mypy pass; the three
owned inputs are unchanged during the final run. Independent review finds no
material issue and verifies generation/cancellation ownership, captured process
and endpoint, interruptible stop and retained handles after failed cleanup.
Forty existing function definitions are AST-identical; two change only the
cancellation type annotation, five lifecycle bodies intentionally change and
three focused methods are added. The existing large implementation remains a
legacy surface; no new oversized facade or size exception is introduced.

T040/T041 final focused execution passes 51 tests in 20.42 seconds, zero skips,
with ESLint passing all eight owned files and no warnings. SearchPage has 57
lines, AgentWorkPage 130, queue controller 180 and detail controller 78. The
independent review confirms mount/request ownership, shared identity/revision
reconciliation, current-filter protection and a server-derived pagination cursor.
An outside-page acknowledgement initially exposes a skipped pagination boundary;
the bounded GET reconciliation and removed-Queued-row tests pass. A Temp replay
of the earlier items.length callback meaningfully fails that boundary case;
its 26 deliberately deselected cases and initial helper import error are retained.
The earlier focused history records 12 failures (including one ambiguous test
selector), then 11 actual regression failures after fixing that selector, before
the passing implementation. No harness failure is presented as a product pass.

The all-change pre-commit execution passes Ruff, Ruff format, global mypy,
frontend ESLint, whitespace/EOF, conflict/large-file and Python-debug checks.
YAML has no matching changed file and is skipped. Command and wrapper both exit
0 after 58.92 seconds, all 1,373 tracked/new inputs unchanged. Every new/changed
production input is frozen before complete backend/frontend execution.

The independent Spec Kit analysis reports 28 FRs, 26 SCs, ten outcomes, twelve
plan decisions, eight constitution principles and 45 tasks; requirement/criterion
coverage is 54/54 with no material gap, duplication, ambiguity or authority
conflict. Final aggregate execution and convergence remain tracked by T044.

### Frozen frontend, browser journeys and native/storage gates

The final complete frontend run passes 803 tests across 114 files with unchanged
coverage thresholds: 84.73% statements, 75.22% branches, 76.75% functions and
89.37% lines. Node runtime contracts, license/distribution/icon checks and global
ESLint pass. Command and wrapper exit 0, with zero differences across 1,260
source/dist inputs. Five existing JSDOM canvas getContext warnings are retained
in the log; no failing test is suppressed and no canvas dependency is added.

The production build and unchanged size gates pass, with 1,216 unchanged source
inputs and 44 generated assets. Raw/gzip byte counts are entry 267,104/82,973,
Italian locale 89,988/28,424, lifecycle CSS 21,837/5,841, initial resources
379,976/117,803, workspace CSS 434,350/72,155 and workspace shell 17,140/5,785.

All eight final E2E groups pass in 132.284 seconds, npm and wrapper both exit 0,
with no remaining attributable test processes or vaults and no differences
across 1,260 source/dist inputs. The identified wrapper and its own conhost
console are independently absent by PID plus creation time after exit. No
process is killed. The 1,216 source and 44 final asset hashes still match their
frozen manifests. These journeys cover portfolio, agenda, login, agent access,
agent work, application materials, providers and responsive workspace shell.

Native fmt, clippy with warnings denied and all 28 Rust tests pass, with zero
differences across 70 native inputs. The isolated desktop suite passes 32 tests
with six skips: five POSIX contracts and one artifact-only case requiring
CAREEROS_SIDECAR_BINARY. Pytest and wrapper return 0; all 1,216 inputs match.
Fresh Alembic upgrade, downgrade one revision and upgrade pass, SQLite integrity
is valid and foreign-key violations are zero, with all 1,216 inputs unchanged.

Python 3.12.13 has exactly the 121 installed distributions required by the
runtime/development/tooling lock union; pip check passes. The first read-only
attestation helper incorrectly ignored requirement extras and reported four
apparent additions. Its corrected optional-extras parser proves zero missing,
extra or version-mismatched packages. Both helper outputs are retained; no
dependency is installed or changed. Node is 24.18.1 and Rust is 1.96.0.

The actual production browser checks pass all eight scenarios: English/Italian
at 390/1,440 px for search ownership and agent-work reconciliation. Search
checks wait for Jobs/Annunci content to mount, confirm the abandoned client
request closes, then release the accepted server acknowledgement; there is no
redirect, automatic retry or server cancellation. Queue checks retain 24 Queued
cards after cancellation and all 25 cards with current revisions in All.
Twelve final screenshots pass visual review, including four independently
inspected by the coordinating reviewer. Page errors, external requests,
unexpected APIs/mutations and server errors are zero. Browser console output
was not collected separately and is not claimed as a passing console gate.

The first 105-assertion probe returned success but captured search during lazy
route loading. Its four search captures therefore do not establish unmount
ownership. All original outputs are retained; four strengthened search cases
with 46 assertions supersede only those cases. The original four queue cases
remain valid. Every invocation preserves 1,216 source files, 44 build assets
and eight owned files; browser/server processes are closed and their recorded
identities are absent. No production change or destructive cleanup is needed.

### Final complete backend and performance

The complete frozen Windows backend run passes 3,020 tests with 17 skips in
1,764.82 seconds. Combined branch-aware coverage is 82.31%, above the unchanged
80% gate. Pytest and the strict outer caller both return 0; the runner takes
1,841.313 seconds including collection/setup and all 1,216 source inputs are
unchanged. Thirteen skips cover POSIX ownership/mode, no-follow, ctime, FIFO and
fcntl contracts; four are opt-in performance cases run separately below.

The explicitly enabled performance run passes all four tests with no skips in
13.22 seconds, command and caller both return 0, with 1,216 unchanged inputs.
Readiness p95 is 25.138 ms against 100 ms and uses at most five queries. At 10,000
records, profile/application-page/agenda reads take 7.357/53.908/129.510 ms against
200 ms. Generation and detailed-resume reads satisfy their existing 500/200 ms
assertions; those tests do not emit numeric timings, so no exact value is claimed.

All implementation tasks have independently reviewed RED/green evidence. Final
read-only convergence finds all 54 requirement/criterion entries covered across
45 tasks, with no missing, partial, contradictory or unrequested implementation.
It appends no task and preserves task bytes; the coordinator records T044's
completion separately. Protected PR checks, signed-main identity, recovery
bundles and ref cleanup remain subsequent executions, not inferred passes or a
production release.

## Protected Linux fixture correction on PR #119

Source a66b020 is preserved in a complete verified recovery bundle. Its CI run
39061460124 fails the backend step: 3,017 tests pass, 11 skip and nine error during
claim_vault setup in 722.76 seconds, with 83.86% combined coverage. No promotion
assertion in those nine cases executes. The subsequent performance step is
skipped because the test step failed. The other seven CI jobs succeed; CodeQL
passes four languages and its aggregate check, and Desktop packages passes nine
jobs with two intentional release-assembly/publication skips. Those successes
do not make the failing head eligible for merge.

Two independent reviews trace the fixture to create_engine/configure_sqlite_connection
without the existing ensure_sqlite_parent bootstrap. The POSIX validator rejects
that newly created database before create_all. The CI traceback does not report
an actual lstat mode, so no measured permission value is claimed. T046 reuses the
canonical private bootstrap already used by other real SQLite fixtures; no
production validator, security assertion or coverage gate is relaxed.

The corrected focused Windows suite passes 33 tests with no skips in 28.44
seconds. Ruff check and format pass; the required backend mypy command returns
0 with no output. An additional direct mypy check on the test returns 1 with
three annotation diagnostics; the original a66b020 test reproduces exactly the
same messages, shifted by the two added lines. This optional check is not
reported as passing, and its outer caller's exit 1 is preserved. A report helper
initially expected a log from the silent successful backend mypy command;
the missing empty log is recorded and replaced by explicit exit/output metadata,
without rerunning or reclassifying any check.

The sole non-Markdown delta is this fixture. All other 1,215 frozen inputs and
44 build assets are unchanged; removing the exact bootstrap delta yields an
identical module AST, including every assertion. The complete Windows run above
remains attributed to a66b020, not to this changed fixture. Independent analysis
and convergence cover 46 tasks, thirteen decisions and all 54 FR/SC entries,
append no task and preserve task bytes during review. T046 completion records
the reviewed source hand-off. Renewed full Linux and all protected checks on
the corrected PR head remain mandatory before merge, and their actual results
will be recorded in PR metadata and the private recovery ledger.

## Quality follow-up, 2026-10-20

This cycle starts from signed main dee0e5e after PR #119 completed its protected
and post-merge checks. Historical results above remain attributed to their
original inputs. Before T053/T054 the source has 1,220 non-Markdown inputs; the following
coordinated checks preserve all of them byte-for-byte. Synthetic data, logs,
coverage helpers and browser outputs remain in the operating-system temporary
directory. No personal reference directory is accessed.

| Check | Actual result |
| --- | --- |
| Backend resumes, security and profile integration | 305 passed, no skips, 169.30 seconds |
| Backend/scripts Ruff and mypy | Both exit 0; direct mypy on both changed regression modules also exits 0 |
| Changed Python formatting | Pass; the additional repository-wide format check fails as detailed below |
| Frontend `npm test` | 818 tests in 115 files pass; four Node runtime tests and eleven license/distribution tests also pass |
| Frontend `npm run lint` | Exit 0 |
| Production build and unchanged bundle validator | Pass; 44 assets, final notices byte-identical, locale and entry budgets unchanged |
| Rust fmt, Clippy with warnings denied, tests | All exit 0; 28 tests pass; 70 native inputs unchanged |
| Alembic upgrade head, downgrade one, upgrade head | Pass; SQLite integrity is OK, foreign-key violations are empty, head d0b1c2d3e4f5 |
| Desktop Python tests, corrected runner | 32 passed, 6 skipped, 19.78 seconds |
| Explicit performance acceptance | 4 passed, no skips, 9.51 seconds |
| Python audits: runtime/development/tooling | All exit 0 with zero findings; inventories 58/112/21 packages |
| Fresh-cache npm audit and exception validator | Both exit 0; no findings |
| Dependency/notices/wheel focused checks | 23 passed; Ruff, format and mypy pass |
| Real isolated agent wheel | Build and metadata/installed-dependency check pass; unsigned, not published |
| Schedule browser EN/IT at 390/1,440 px | Four scenarios, 69 assertions pass; eight screenshots reviewed |

The browser verifies acknowledged interval changes, a failed optional overview
read, both retained rows and keyboard-only GET retry. Four deliberately injected
HTTP 503 responses, four browser resource-error messages and four content-free
diagnostic codes are expected; unexpected page errors, API calls, mutations and
external requests are zero. All 44 build assets and seven owned UI files remain
unchanged. Browser/server process identities are absent after cleanup. The
coordinating reviewer independently inspected the English mobile and Italian
desktop warning captures; the implementation reviewer inspected all eight.

T048 first reproduces seven failing cases and ten positive controls on the
original synchronization implementation. Its final focused suite passes 54 tests
with no skips. The fix rejects cached stale revisions and deletion state,
refreshes profile facts, and validates the response before commit. Independent
review finds no actionable issue in production code or rollback/ownership tests.
T049 passes 39 repository cases plus four replayed audit cases; independent
review verifies lifecycle ownership, nullable interval normalization, current
server-read authority and preservation of accepted writes on refresh failure.
T047 retains all twenty original assertions and adds one positive canvas guard;
the three formerly failing type diagnostics are gone and all five telemetry
controls remain false.

The new strict hash-installed Python 3.12.13 environment has exactly 121 packages
matching the compatible union of the three locks. The previous environment is
unchanged. Pydantic 2.14.1 requires pydantic-core 2.50.1. Fresh scans initially
fail on certifi 2026.6.17 for GHSA-6q48-6c7w-9gw2, published on 2026-10-20;
the officially fixed 2026.10.19 release is installed and all three scans then
pass without suppression. Canonical notices contain 13 frontend, 58 Python,
three runtime and 473 Rust records, 1,424,429 bytes, SHA-256
ee2f5e6720b1eaa41a17ddec8bb8ff5d1d66dc22fd55dc35da0264c42e0147de.
The isolated unsigned wheel is 1,054,691 bytes, SHA-256
de669486685417e102379cd84f3dfa9b8b04219b75d5c4755cf203d96021b263;
its metadata agrees with the regenerated locks. No installer is released.

The Rust security guard still returns 1: CE-2026-001 expired on 2026-10-19.
The stable Tauri/GTK graph still includes glib 0.18.5; the upstream advisory
requires a patched version at least 0.20.0. A diagnostic-only copied lock proves
that marking the unchanged package as a path dependency makes cargo-audit omit
it. That is a scanner blind spot, not remediation, and is not applied. No expiry,
ignore, advisory policy, Cargo source or package version is changed. Security
publication remains blocked independently of the passing Rust code checks.

The extra full `ruff format --check backend tests/backend scripts` returns 1:
84 files would change and 574 are already formatted. Independent read-only
comparison proves all 84 are unchanged from dee0e5e and use the same Ruff/config.
Formatting copies preserves all AST statements and forty type-ignore tags and
bindings (two initial AST differences are line coordinates only). However four
modules would grow beyond 300 lines. At this stage no bulk patch is applied or
represented as a passing check. T053/T054 below then address this observed gap.

Preserved unsuccessful executions include: the initial root focused invocation
with an incorrect test path (exit 4, zero tests), followed by the corrected
12-pass invocation; the first external audit runner's Windows symlink shutdown
error; UI probe setup, encoding and mock-isolation failures; the scoped synchronization
mypy nullable-local diagnostic, corrected by normal narrowing; and the original
desktop runner lacking a multiprocessing main guard (31 passes, one failure,
six skips). The corrected desktop runner changes only temporary tooling and
passes the actual second-process lease assertion. Five desktop skips concern
POSIX contracts; the sixth requires a packaged sidecar supplied by artifact CI.
No failed or skipped execution is reclassified as passing.

A complete new Windows backend run is not claimed. Full Linux backend coverage,
frontend coverage/eight E2E groups, four platform/interpreter wheel checks and
protected supply-chain jobs must be measured on the new PR head. Their results
belong in PR metadata and the private recovery ledger. Merge and branch cleanup
remain blocked until mandatory security prerequisites pass.

## Final decomposition and canonical formatting, 2026-10-20

T053 extracts snapshot projection, import acknowledgement construction, XLSX
part resolution and portable campaign-artifact validation. Independent review
reconstructs the original parent bodies from the new helpers and verifies
unchanged public imports, callbacks, validation order, transaction boundaries
and error messages. The eight resulting modules have 216, 285, 103, 29, 294,
79, 285 and 114 lines. No schema or product-authority change is introduced.

T054 applies pinned Ruff formatting: the command reports 80 files reformatted
and 582 unchanged. The 80 are exactly the original 84 minus the four already
decomposed and formatted modules. The independently recomputed proof covers
all 661 Python files in backend, tests/backend and scripts: executable ASTs and
all 98 type-ignore tags/statement bindings are identical across formatting,
including the forty bindings in the original 84-file audit. No non-formatting
source change is hidden in that bulk patch.

The final source manifest contains 1,224 non-Markdown inputs. Complete Ruff,
mypy, direct regression-test mypy and repository-wide format checks all return
0 in 32.015 seconds, with no input changes. All applicable pre-commit hooks
pass in 24.469 seconds without mutation; YAML is skipped because no YAML file
changed. The final documentation-only reconciliation is checked separately.
Independent scoped comparison confirms 408 frontend inputs, 70 native inputs
and all 44 built assets remain byte-identical to their successful checks above.

A new isolated wheel is built after the extractions and formatting. It contains
all 397 backend/desktop Python files, including the four new helpers, plus
declared data, byte-identical to the final source. All 403 packaging inputs and
the 121-package environment remain unchanged. Its twenty dependency entries
match pyproject metadata, dependency verification returns 0, and packaged
notices retain the approved hash. The unsigned wheel is 1,057,664 bytes,
SHA-256 74b2471d7e8f66bfdf72c3951e6940dc753ed27f4d825055e08fe99cab2e28ad.
The earlier wheel remains historical evidence of T051, not the final payload.

Final independent code/format review is GOOD, with no material findings;
SHA-256 1fabd43f3955ea35cf29cdf4a15c77885b497e6862ac6e5b4e3fed766c1fc7ee.
Independent artifact review verifies 60/60 requirement/criterion mappings and
54 tasks; its two documentary observations are reconciled before the hand-off.
T050 and T052 remain open for the actual security blocker and protected
integration. Historical policy-blocked cache cleanup is preserved without retry.

The final aggregate campaign, portability, security and release regression
passes all 690 tests with no skips in 433.29 seconds. Its caller returns 0 in
444.0 seconds, and all 1,224 inputs remain unchanged. T053/T054 source review
and local validation are complete; protected qualification remains T052.
