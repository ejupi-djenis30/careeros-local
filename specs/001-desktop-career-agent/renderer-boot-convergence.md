# Measured offline renderer boot — convergence

Date: 2026-07-30

Decision: the constitution, specification, plan, task list, production graph, generated assets,
browser acceptance and distribution configuration now describe one bounded offline renderer boot.
The login route loads one selected local catalogue, uses only audited icon geometry and fails the
build when measured startup budgets regress.

| Area | Converged behavior | Result |
| --- | --- | --- |
| Language graph | English and Italian are independent bundled chunks; the selected catalogue alone loads at boot | Converged |
| Async lifecycle | Registry deduplicates imports; StrictMode remains safe; pending switching, EN fallback and localized explicit retry are tested | Converged |
| Failure containment | Dual import failure performs no automatic reload or retry loop and focuses the user-controlled retry | Converged |
| Icons | 123 explicit Bootstrap SVGs generate one attributed, stale-checked CSS mask subset; no icon font is emitted | Converged |
| Payload | Entry is 340,810 B raw / 107,495 B gzip and worst-case initial resources are 849,184 B / 202,124 B | Converged |
| Budget enforcement | Entry, locale, CSS and initial raw/gzip ceilings run after every production build | Converged |
| Mobile login quality | 44 px language targets, visible keyboard focus, 7.60:1/7.96:1 corrected contrast and zero axe violations pass in Chromium | Converged |
| CSP delivery | Framing is absent from ineffective meta policy and retained in Nginx response headers; native CSP is unchanged | Converged |
| Update policy | All five Dependabot ecosystems have a seven-day routine-update cooldown | Converged |
| Release shell boundary | Repository, tag and commit enter quoted Bash arguments only through workflow environment variables | Converged |
| Proxy identity | Backend receives fixed Host `localhost`, not the client-supplied Host | Converged |
| Supply-chain exception | Linux-only glib 0.18 is unreachable at known affected call sites, cannot be lock-updated under current Tauri/GTK constraints and remains pinned to expiring `CE-2026-001` | Bounded through 2026-10-19 |
| Regression evidence | 405 frontend tests, 1,582 backend tests, 4 isolated performance budgets, 17 Rust tests, all browser gates and migration round-trip pass | Converged locally |

T180–T186 are complete. The remaining Bootstrap CSS modularization opportunity, GitHub-hosted
workflow execution, platform packaging/signing smoke, first supported Tauri/GTK migration beyond
the expiring glib exception and live local-model evaluation are bounded follow-ups rather than
claims made by this slice. The complete local tree remains intentionally uncommitted and unstaged;
no commit, merge, push, release or deployment was performed.
