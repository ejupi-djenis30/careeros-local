# Mandatory local analysis — convergence

Date: 2026-07-23

Decision: the constitution, specification, plan, tasks, backend, desktop interface, portability
contract and public documentation converge on one rule: features presented as AI analysis require a
ready local model and fail closed. Deterministic ownership workflows remain available without it.

| Area | Converged behavior | Result |
| --- | --- | --- |
| Product language | No optional-AI or cloud-fallback claim remains in the owner-facing product paths | Converged |
| Runtime | Managed local model lifecycle and readiness diagnostics are first-class desktop features | Converged |
| Analysis | Strict score output is validated before server policy derives decisions and citations | Converged |
| History | Only locally validated, provenance-bearing assessments appear as completed analysis | Converged |
| Coach | Responses are reconstructed from validated claims tied to Career Vault evidence IDs | Converged |
| Portability | Untrusted historical or imported analysis and Coach replies are preserved in quarantine across snapshot, export and restore | Converged |
| Account isolation | Discovery queries live on each user-owned saved job, never on the shared provider listing | Converged |
| Security | Inference remains on loopback or an exact explicit local-container alias | Converged |
| Recovery | Setup, retry and diagnostics remain accessible without hiding model-independent work | Converged |
| Quality gates | Backend, frontend, Rust, migration, static, performance and real-runtime checks passed | Converged locally |

Publication still requires protected-branch CI and the existing signed-tag release workflow on the
exact merged commit. No manual artifact may bypass those controls.
