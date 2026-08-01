# Coordinated desktop shutdown analysis

## Purpose

CareerOS owns a Python/FastAPI sidecar which can in turn own the scheduler, active search tasks
and a managed local `llama.cpp` process. The previous native exit handler immediately killed only
the Python child, while the Python parent watchdog called `os._exit(0)`. Both paths could bypass
FastAPI lifespan cleanup and leave descendant work or a managed runtime behind. This slice makes
graceful cleanup the normal and crash-recoverable path without allowing application exit to wait
forever.

## Required invariants

- The control surface stays on the existing IPv4 loopback listener and accepts the same random,
  per-launch desktop session token as every other native request.
- Browser mode cannot use the route, the route is absent from OpenAPI, and neither the token nor
  private shutdown details enter logs or persistence.
- A first native exit request is prevented until the supervisor has observed sidecar termination
  or a fixed timeout has expired. Repeated exit requests start no duplicate shutdown worker.
- Uvicorn receives a graceful signal first and is allowed to run FastAPI lifespan cleanup. The
  native shell retains a hard termination path for a wedged server.
- Parent loss follows the same graceful Uvicorn path before the Python watchdog's hard exit.
- The supervisor cannot restart a sidecar after shutdown begins, including the narrow race where
  shutdown starts while process spawning is still completing.
- Windows descendants share a kill-on-close Job Object. Failure to establish that containment
  fails sidecar startup instead of silently running without the promised boundary.

## Protocol

### Normal native exit

1. Tauri receives `ExitRequested`, derives the final normal or packaged-smoke exit code and calls
   `prevent_exit` unless shutdown was already completed.
2. One atomic state transition marks the lifecycle as shutting down. The supervisor therefore
   stops restarting failures and rejects an in-flight spawn.
3. A bounded native worker sends `POST /api/v1/desktop/shutdown` to `127.0.0.1` with
   `X-CareerOS-Session` and no body. The token is never placed in process arguments or logs.
4. `DesktopSessionMiddleware` performs the existing constant-time authorization. The hidden route
   invokes the controller bound to the one active Uvicorn server and returns `202`.
5. The controller sets `server.should_exit`. Uvicorn drains with a 20-second graceful timeout and
   executes the FastAPI lifespan shutdown, including scheduler stop, active-search cancellation
   and managed-runtime stop.
6. The shell supervisor consumes the termination event, clears the child and Windows job, declines
   restart because shutdown is active, and marks itself stopped.
7. When both child and supervisor are stopped, the shutdown worker marks completion and calls
   `app.exit` with the preserved exit code. The second `ExitRequested` is then allowed through.

The shell deadline is 30 seconds, leaving Uvicorn's bounded drain time plus process-exit overhead.
If that deadline expires, Tauri kills the direct child, closes the Windows Job Object to terminate
descendants, waits at most another two seconds for supervisor settlement and exits.

### Native-parent disappearance

The Python watchdog polls its parent. When the parent is gone it sets the same Uvicorn shutdown
flag and waits on a server-completion event for at most 30 seconds. Only an incomplete drain reaches
`os._exit(0)`. This keeps crash recovery bounded while preserving lifespan cleanup whenever the
event loop remains responsive. On Windows, abrupt Tauri termination closes the last native Job
Object handle and the operating system can terminate the assigned tree before Python observes the
parent loss. That immediate containment intentionally takes precedence over graceful crash cleanup;
the watchdog remains the recoverable path where OS containment has not already acted.

## Boundary and race review

| Risk | Control |
| --- | --- |
| Browser or unrelated local page stops the backend | Browser mode returns `404`; desktop mode requires the unpersisted per-launch token |
| Shutdown request waits behind vault maintenance | `POST /desktop/shutdown` bypasses the vault reader gate while retaining session authentication and private no-store headers |
| Repeated window-close events start competing workers | Atomic `begin_shutdown` admits only the first worker; every incomplete exit remains prevented |
| Sidecar spawns after shutdown begins | The supervisor checks before spawn and again while installing the new child into shared state; the raced child is killed and never monitored as ready |
| Receiver fails before a termination event | The still-owned child is explicitly killed before containment is released |
| Graceful request is lost during startup | The worker retries while a child remains and still has a fixed global deadline |
| FastAPI cleanup hangs | Uvicorn, native worker and parent watchdog each retain explicit upper bounds |
| Python dies while its local runtime survives on Windows | Closing the configured Job Object terminates all assigned descendants |
| Job Object setup is unavailable | Windows sidecar startup fails closed; no unconstrained child is accepted into lifecycle state |
| Packaged smoke requests a nonzero exit | The requested smoke result is preserved across asynchronous cleanup |

The shutdown route is transport only: it does not decide domain state and it holds no vault reader
permit. It delegates to a process-local controller that exists only while the frozen entry point's
Uvicorn server is running.

## Implementation mapping

- `backend/api/routes/desktop.py`: single-server shutdown controller and hidden desktop-only route.
- `backend/api/api.py`: route registration under `/api/v1/desktop`.
- `backend/api/middleware.py`: maintenance-path bypass so shutdown cannot deadlock behind a writer.
- `desktop/backend_main.py`: bound Uvicorn controller, 20-second graceful timeout and ordered
  parent-watchdog fallback.
- `frontend/src-tauri/src/lifecycle.rs`: authenticated loopback request, exit state machine,
  supervisor race handling, bounded force path and Windows Job Object containment.
- `frontend/src-tauri/src/lib.rs`: Tauri exit prevention and final-exit handoff.
- `tests/backend/desktop/test_shutdown.py`, `tests/desktop/test_backend_entry.py` and Rust unit tests:
  authorization, controller binding, browser absence, watchdog ordering, request shape and
  idempotent lifecycle state.

## Focused evidence

- Python lifecycle selection: 30 tests passed, including preservation of a pointer-sized Win32
  parent handle through the configured `ctypes` signatures.
- Python static checks: focused Ruff and Mypy passed.
- Rust unit suite: 19 tests passed, including token-bearing loopback shutdown transport and
  idempotent completion state.
- Rust formatting and Clippy with warnings denied passed on Windows ARM64.
- Cargo license policy passed.
- Lock-bound notices regenerated and verified at SHA-256
  `51034e32f2d2504fdcbde7385732e19ec2266c20a7c5146e1b0a6c8d3a355775`; eight notice tests passed.
- Frontend license/distribution contracts passed six tests under Node 24.18.0, and the generated
  123-icon subset remained current.

## Residual limits

- The focused suite uses an in-process FastAPI client and a synthetic TCP peer. It does not replace
  the existing packaged installer lifecycle matrix for proving real process-tree cleanup on every
  operating system.
- Windows Job Object code compiled and passed Clippy on Windows ARM64, but this slice did not launch
  a packaged sidecar plus real `llama.cpp` child to force the hard-timeout branch.
- On non-Windows platforms the hard fallback terminates the direct sidecar; descendant cleanup is
  guaranteed by the tested graceful lifespan path and remains subject to the packaged zero-orphan
  release acceptance gate if the process is unresponsive past all graceful bounds.
- The shutdown worker's 30-second drain plus two-second settle can be exceeded by at most one
  already in-flight bounded loopback attempt (300 ms connect plus 500 ms read and write timeouts).
  This finite integrity tradeoff remains below 34 seconds in the worst path; it is not an
  instant-close guarantee.
