# Coordinated desktop shutdown convergence

## Scope

This review converges Constitution Principle I, User Story 1 acceptance scenario 3, FR-002,
SC-009, plan Phase B and tasks T015/T016/T019/T022 with the implemented native-sidecar shutdown
protocol. It covers normal Tauri exit, Python parent loss, bounded forced fallback and Windows
descendant containment. It does not substitute focused unit evidence for the multi-platform
packaged lifecycle release matrix.

## Requirement mapping

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Token-authenticated local control | Hidden `POST /api/v1/desktop/shutdown` on the existing loopback API and `DesktopSessionMiddleware` | Missing/wrong token `403`, valid token `202`, browser mode `404` |
| FastAPI lifespan cleanup before normal exit | Bound controller sets `uvicorn.Server.should_exit`; Uvicorn has a 20-second graceful timeout | Controller invocation test plus backend-entry configuration/static review |
| Shell remains alive during cleanup | First `ExitRequested` is prevented; completion triggers the final `app.exit` | Rust idempotent begin/completion state test and exit-handler review |
| Fixed hard upper bound | Tauri waits 30 seconds then forces termination and settles at most two seconds | Constant and branch review; Rust formatting/Clippy compilation |
| Parent-crash recovery | Python watchdog requests the same Uvicorn stop and waits 30 seconds before `os._exit`; abrupt Windows parent loss may instead close the Job Object first | Two watchdog tests prove graceful completion avoids force and timeout invokes force; packaged crash containment remains required |
| No shutdown restart race | Supervisor checks shutdown before spawn and before publishing the child; shutdown disables restart | Shared-state/supervisor review and bounded restart unit coverage |
| Receiver failure does not detach a live child | A channel close/error without `Terminated` consumes and kills the retained child | Rust ownership-path review and Clippy with warnings denied |
| Windows descendant containment | Per-child Job Object uses `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`; assignment failure fails startup | Windows ARM64 compile, 19 Rust tests and Clippy; packaged forced-tree smoke remains a release gate |
| Vault maintenance cannot block process control | Shutdown route bypasses only the vault activity reader gate, retaining token/host/private-response middleware | Middleware set review and focused vault-activity regression selection |
| Dependency/legal evidence stays lock-bound | Direct `windows-sys` features are declared for the Windows target and notice bytes are regenerated | Cargo deny, deterministic notice check, notice tests and frontend distribution contract |

## Cross-artifact findings

- The constitution now requires an ordered, bounded shutdown and termination of child processes
  even when the graceful path fails. FR-002 names the authenticated request, watchdog and Job
  Object mechanisms that implement that policy.
- The specification does not promise instant close: SC-009 requires zero orphans and a finite
  lifecycle bound. Plan Phase B uses the same 20/30/2-second layering as implementation.
- Existing task identifiers remain stable. T015/T016 cover the new failure cases; T019/T022 name
  the Python route/watchdog and Rust exit/containment work respectively.
- The route stays in the transport layer and delegates to a process-local controller. Vault,
  scheduler and runtime shutdown policy remains in FastAPI lifespan code.
- The per-launch token is supplied only as an HTTP header. It is absent from child arguments,
  persistence, error messages and logs.
- The activity-gate exception does not weaken authentication or cache policy: it prevents a
  control-plane deadlock while outer middleware still authorizes and marks the response private.
- Packaged-smoke exit codes remain truthful across asynchronous cleanup.

## Proportional validation

| Gate | Command | Result |
| --- | --- | --- |
| Focused Python lifecycle | `.venv/Scripts/python.exe -m pytest tests/backend/desktop tests/desktop/test_backend_entry.py tests/backend/unit/test_vault_activity.py -q` | 30 passed, including the 64-bit Win32 handle-signature regression |
| Focused Python lint | `.venv/Scripts/python.exe -m ruff check backend/api/api.py backend/api/routes/desktop.py desktop/backend_main.py tests/backend/desktop/test_shutdown.py tests/desktop/test_backend_entry.py` | Passed |
| Focused Python typing | `.venv/Scripts/python.exe -m mypy backend/api/routes/desktop.py desktop/backend_main.py` | Passed |
| Rust formatting | `cargo fmt --all -- --check` | Passed |
| Rust unit suite | `cargo test --lib` | 19 passed |
| Rust lint | `cargo clippy --all-targets --all-features -- -D warnings` | Passed |
| Cargo license policy | `cargo deny --all-features check licenses` | Passed |
| Deterministic notices | `.venv/Scripts/python.exe -m scripts.third_party_notices --check` | Passed; frontend 12, Python 55, runtime 2, Rust 484 |
| Notice regression | `.venv/Scripts/python.exe -m pytest tests/backend/release/test_third_party_notices.py -q` | 8 passed |
| Frontend license/distribution contract | Node 24.18.0 `npm run test:licenses` | Six contract tests passed; 123-icon subset current |

## Execution notes

The first Cargo unit command stopped at Tauri's expected generated-resource precondition because
`frontend/src-tauri/binaries/careeros-backend-runtime` was absent. Creating that ignored build
directory allowed the crate tests to run; no placeholder binary or tracked artifact was added.

The system Node executable was 24.16.0 and correctly failed the project's executable preflight, so
that diagnostic run did not execute the distribution contract. The authoritative rerun used Node
24.18.0 from an npm-provided local runtime and passed. The supported runtime floor was not lowered.

Adding the explicit Windows API dependency changed `Cargo.lock`. The deterministic notice generator
was run with the pinned Python 3.12.13 environment after installing its locked PyInstaller tooling.
The approved notice digest is now
`51034e32f2d2504fdcbde7385732e19ec2266c20a7c5146e1b0a6c8d3a355775`.

No installer was built, no real managed model process was started, and no packaged hard-timeout
process-tree test was run in this slice. No commit, push, release or deployment was performed.

An additional API/main/origin regression selection passed 66 tests and failed one pre-existing
access-session fixture: `test_api_misc_routes.py::test_deps_full` supplied `sub` and `sid` but not
the newly mandatory access `purpose` claim, so the live-authority dependency correctly returned
`401`. This result is reported as a failure and was handed to the access-session owner; it does not
invalidate the isolated shutdown route, middleware or lifecycle results above.

## Result

The focused desktop shutdown slice is converged: policy, specification, plan, tasks, Python control
plane, Rust lifecycle, dependency evidence and proportional tests agree. The remaining proof is
the existing cross-platform packaged lifecycle matrix, especially a forced Windows process-tree
case with a real managed runtime; it remains a release control rather than a locally verified claim.
