# Renderer CSS boundary convergence

## Closed findings

- Login, localization, recovery and native boot no longer fetch workspace layout, feature,
  full-icon or Bootstrap CSS.
- The nine lifecycle icons and 123 workspace icons are generated and drift-checked independently;
  neither path emits the Bootstrap Icons font.
- The authenticated boundary explicitly owns the complete icon, legacy, CareerOS and layered
  Bootstrap sheets in the established cascade order.
- Initial and lazy CSS are each emitted as one asset and enforced by raw/gzip budgets.
- Initial CSS contains login, recovery, native boot, forced-colors, reduced-motion and mobile
  lifecycle behavior while representative workspace selectors are rejected.
- Lazy CSS retains workspace layout, home and agent-access sentinels plus print, forced-colors,
  reduced-motion and 1,450/720/480 px responsive contracts.
- The recovery input primitive formerly supplied implicitly by global legacy CSS is now explicit in
  the lifecycle sheet and passes real-browser touch-target and overflow checks.

## Executable boundaries

The delivery graph is anchored by `frontend/src/main.jsx` and
`frontend/src/app/AuthenticatedWorkspace.jsx`. Icon drift is enforced by
`scripts/build_frontend_icons.mjs`; source-level import order by
`scripts/frontend_distribution_contract.test.mjs`; emitted asset counts, selectors, media and
budgets by `scripts/validate_frontend_bundle.mjs`.

No backend service, provider, native process, installer, commit, push or deployment was used for
this slice. The E2E fixtures opened only loopback ephemeral ports and closed them in `finally`.

## Residual measurement boundary

The production artifacts and request graph are converged locally. A future trace-capable
environment may add cold-load CWV timings, but Chrome DevTools MCP was not configured here and no
timing claim was substituted for it. Installed Tauri and packaged web-server cache/compression
behavior remains covered by the release matrix and existing distribution contracts.

