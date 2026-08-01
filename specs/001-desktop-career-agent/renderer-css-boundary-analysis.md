# Renderer CSS boundary analysis

## Scope and method

This slice audits only the renderer delivery graph for login, localization failure, vault recovery,
native boot and the authenticated workspace. It changes no backend, provider, Rust or release
workflow behavior. Measurements come from fresh Vite production builds under Node 24.18.0 and use
the exact emitted bytes plus deterministic gzip output from the executable bundle validator. Real
Chromium exercises the emitted distribution and records the resources actually requested.

Chrome DevTools MCP was unavailable in this environment, so this slice does not claim new FCP, LCP,
INP, CLS or trace timings. The production artifact and real-browser resource boundary remain
directly measured rather than inferred from source size.

## Reproduced boundary

Before the split, `main.jsx` imported the complete 123-icon SVG mask sheet, legacy `index.css`
and all of `career-os.css`. Login, recovery and native boot therefore received workspace layout,
home, resume, application, search and agent-access rules before authentication. The only lazy
stylesheet was the layered Bootstrap compatibility sheet.

The baseline production graph emitted:

| Surface | Raw | Gzip |
|---|---:|---:|
| Initial CSS | 196,856 B | 40,387 B |
| Worst-case initial resources | 598,395 B | 167,994 B |
| Lazy authenticated CSS | 230,877 B | 30,598 B |
| Initial JavaScript entry | 325,676 B | 103,172 B |
| Largest selected locale | 74,816 B | 23,869 B |

The CSS was valid and already kept Bootstrap lazy, but its delivery boundary did not match the
session boundary.

## Implemented graph

The entry now imports only `shell-icons.css` and `shell.css`. The shell contains theme and focus
primitives, form controls, login, recovery, localization, native boot, lifecycle forced-colors and
reduced-motion rules, and the 991.98/480 px lifecycle breakpoints. Its generated icon graph contains
the nine icons referenced by lifecycle components.

`AuthenticatedWorkspace.jsx` imports, in order:

1. the complete generated 123-icon subset;
2. legacy `index.css`;
3. the established `career-os.css` design system;
4. layered Bootstrap compatibility CSS.

Keeping the complete CareerOS sheet after the legacy sheet preserves the established authenticated
cascade. The small lifecycle declarations intentionally remain available after authentication;
no workspace rule was reordered or weakened for the optimization.

The production validator now proves one HTML-linked lifecycle stylesheet and one lazy workspace
stylesheet, rejects representative workspace selectors and Bootstrap from initial CSS, requires
login/recovery/boot and lifecycle media contracts there, and requires workspace selectors, print,
forced-colors, reduced-motion and all representative viewport contracts in the lazy sheet.

## Measured result

| Surface | Before raw/gzip | After raw/gzip | Change |
|---|---:|---:|---:|
| Initial CSS | 196,856 / 40,387 B | 21,837 / 5,841 B | -88.9% / -85.5% |
| Worst-case initial resources | 598,395 / 167,994 B | 424,563 / 133,956 B | -29.1% / -20.3% |
| Lazy authenticated CSS | 230,877 / 30,598 B | 427,732 / 70,792 B | deferred from initial |
| Initial JavaScript entry | 325,676 / 103,172 B | 326,863 / 103,685 B | +1,187 / +513 B |
| Largest selected locale | 74,816 / 23,869 B | 74,816 / 23,868 B | unchanged |

The initial path saves 175,019 raw and 34,546 gzip CSS bytes. The lazy sheet grows because it now
owns the complete styles that previously blocked login; the final authenticated state also retains
the 21,837-byte lifecycle sheet already used to reach it. This is an explicit, bounded tradeoff for
removing workspace payload from every unauthenticated and recovery load.

The ratcheted ceilings are 23,000/6,200 bytes for lifecycle CSS, 440,000/140,000 bytes for complete
initial resources and 445,000/73,500 bytes for lazy authenticated CSS.

## Regression discovered during convergence

The first real-browser recovery run exposed one genuine implicit dependency: `.form-control`
height and geometry had come from global legacy CSS. At 320 px, the recovery erasure input collapsed
to 27 px. The lifecycle sheet now owns the exact required height, border, padding and radius
primitives; the repeated browser run proves at least 43 px target height and zero horizontal
overflow at 320, 390 and 768 px.

## Verification evidence

- Node 24.18.0 `npm test`: 78 Vitest files and 473 tests passed; four runtime-contract tests,
  six license/distribution tests and both generated icon subsets also passed.
- Node 24.18.0 `npm run lint`: passed.
- Node 24.18.0 `npm run build`: passed all raw/gzip, selector, media and lazy-boundary contracts.
- `npm run test:login-quality`: passed real Chromium login, recovery, forced-colors and production
  workspace checks from 320 through 1,440 px; measured contrast was 7.60:1 and 7.96:1.
- `npm run test:shell-responsive`: passed workspace geometry at 320, 390, 768 and 1,280 px plus
  reduced-motion transition suppression.
