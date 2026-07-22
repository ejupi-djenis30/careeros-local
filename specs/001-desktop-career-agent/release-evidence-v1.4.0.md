# CareerOS Local v1.4.0 release preparation

Date prepared: 2026-07-23

Status: local release-candidate implementation verified. Protected-branch CI, native rehearsal and
the signed-tag publication workflow remain the remote release gates.

Cross-artifact result: [mandatory local analysis convergence](mandatory-local-analysis-convergence.md).

## Candidate scope

v1.4.0 makes local language-model analysis a truthful product requirement. Opportunity search,
matching, recommendation and Career Coach remain locked until an approved model passes structured
readiness probes. The application never substitutes a heuristic or cloud service. Career Vault,
manual records, documents, portability and deterministic application readiness remain usable when
the runtime is unavailable.

The model supplies a narrow seven-score proposal. CareerOS owns requirement extraction, risk caps,
final recommendation, worth-applying decision, citations and persistence. Only verified local-model
executions can appear in job history, application snapshots or restored archives.

All seven authoritative version sources report `1.4.0`; the planned stable tag is `v1.4.0`.

## Local verification recorded for this candidate

- Version contract: `python scripts/check_release_versions.py --expected-tag v1.4.0` passes with
  `RELEASE_VERSION=1.4.0 SOURCES=7`.
- Backend acceptance: 1,261 passed with 4 expected performance skips. Branch-aware coverage was
  80.70%, above the 80% release threshold.
- Python static checks: Ruff passed for backend, tests, migrations and scripts; mypy passed for all
  188 backend source files.
- Frontend: 62 files and 319 tests passed. V8 reported 80.93% line coverage; ESLint, the production
  Vite build and the deterministic production-license audit passed.
- Rust desktop shell: `cargo fmt --check`, locked Clippy with warnings denied and locked tests passed
  (10 tests).
- Migrations: `upgrade head`, `downgrade -1`, and `upgrade head` passed against a fresh disposable
  SQLite vault, including quarantine of historical analysis without verified provenance.
- Performance: all 4 opt-in gates passed. Readiness measured 70.056 ms p95 against 100 ms; the
  10,000-record profile read measured 3.037 ms p95 and the 200-row application page measured
  25.071 ms p95 against 200 ms. Both resume-canvas budgets passed.
- Real runtime: the managed Qwen/llama.cpp path passed all four readiness probes. An independent
  Ollama run completed a natural-language match and evidence-bound Career Coach answer locally.
- Security: explicit container aliases require an exact single-label allowlist match; remote,
  private-network, link-local, malformed, implicit and partial-match targets remain rejected.

## Publication sequence

1. Merge the reviewed candidate through protected `main` with every required check green.
2. Review the read-only native matrix rehearsal on the exact merge commit.
3. Create the verified annotated `v1.4.0` tag with the authorized signing identity.
4. Let the tag workflow build, attest, verify and publish the release; do not alter it manually.
