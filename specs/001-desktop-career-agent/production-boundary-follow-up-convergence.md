# Production boundary follow-up convergence

## Closed findings

- Shared refresh has one 30-second owner-controlled operation. Individual waiters race only their
  own cancellation, so abandoning one caller neither blocks it nor cancels surviving requests.
- Desktop bootstrap propagates owner cancellation through the Tauri invoke wait, retry delay,
  readiness fetch and response-body read. Each probe has a two-second bound and component cleanup
  aborts Strict Mode/unmount work.
- Recovery titles use programmatic `tabindex=-1` focus; logout retry and desktop boot retry receive
  focus when their full-screen states replace prior content.
- Managed-model launch keeps required runtime state, injects its fresh llama key only through the
  child environment, omits it from argv and removes reviewed secret/credential/proxy variables.
- Native smoke failure paths now wait up to 35 seconds for the package-owned sidecar to disappear
  on Windows, macOS and Linux.
- Data-derived external links accept only credential-free HTTPS and validated mail addresses.
  Tauri grants only `https://*` and `mailto:*`; HTTP loopback remains confined to authenticated API
  bootstrap. Job-Room uses exact-origin validation, no redirect following, no ambient proxies and
  retries only transport failures.
- Every ordinary CI evidence upload explicitly retains seven days; every release intermediate and
  final input explicitly retains fourteen days.
- Bootstrap remains one lazy workspace-only CSS layer, tighter raw/gzip budgets pass, and the
  current lock-bound third-party notices reproduce exactly.

## Residual release boundary

The code-level and synthetic contracts are converged. The remaining confirmation is intentionally
external to this local slice: the six-platform release matrix must build and exercise the real
installers and prove zero package-owned processes after success, timeout and failure. No threshold,
security check or test was weakened to obtain the local result.
