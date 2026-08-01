# Mobile workspace navigation isolation — convergence

Date: 2026-07-30

Decision: the constitution, specification, plan, tasks, React shell, sidebar semantics, CSS
acceptance harness and tests now describe one mobile navigation model. The persistent desktop
sidebar becomes a labelled modal drawer only while opened on the mobile layout.

| Area | Converged behavior | Result |
| --- | --- | --- |
| Upstream baseline | Current v1.10 content is present byte-for-byte and retains dossier v6 plus its merged stabilization | Converged |
| Semantics | Open drawer uses a valid labelled `dialog` with `aria-modal`; closed desktop sidebar uses `complementary` | Converged |
| Background isolation | Skip link and workspace are inert and hidden from assistive technology only while open | Converged |
| Scrolling | Existing body overflow is preserved, locked while open and restored on close or unmount | Converged |
| Focus | Initial focus enters the drawer, forward/reverse Tab wrap, Escape closes and connected opener focus returns | Converged |
| Lifecycle | Drawer route activation and the 992 px desktop transition close state and run full cleanup | Converged |
| Scrim | Pointer close remains available without adding a second screen-reader or keyboard target | Converged |
| Motion and layout | Chromium proves no horizontal overflow at 320–1,280 px and suppressed transitions with reduced motion | Converged |
| Runtime payload | Unused Bootstrap JavaScript is absent; CSS and non-interactive theme behavior remain | Converged |
| Static analysis | Alembic is explicitly third-party under locked Ruff 0.16; Ruff and Mypy pass | Converged |
| Regression evidence | 399 frontend tests, 1,573 backend tests, 4 explicit performance budgets, 17 Rust tests and migration round-trip pass | Converged locally |

T175–T179 are complete. The remaining 505.23 kB Vite warning, packaged platform smoke, signing,
protected-branch CI and live local-model evaluation are release/performance follow-ups rather than
claims made by this slice. No commit, merge, push, release or deployment was performed.
