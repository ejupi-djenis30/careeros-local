# Configurable providers and agent-operation parity — cross-artifact analysis

Date: 2026-08-02

## Decision under review

CareerOS Local now starts every Vault with zero network job providers. A source becomes available
only through a user-owned revisioned JSON/HTML declaration or an explicit import of a strict
provider/provider-pack document. The discoverable Swiss pack externalizes Job-Room, SwissDevJobs
and Adecco as dormant references to a closed reviewed-adapter factory and also supplies reviewed
data-only declarations for canton and specialist boards; it installs nothing by default and
manifest data cannot supply executable modules or paths. Imports default to disabled, and an enabled
installation revision is the sole active consent to network requests.

The agent interface is no longer a read-only projection. Twelve granular scopes expose typed
career, job, provider, search, resume and application operations, including ordinary revisioned
mutations. This lets an authorized agent configure a source, run locally analyzed searches,
inspect jobs, create truthful application materials and record application progress through the
same domain services used by the desktop. Grant management, arbitrary files/SQL, backup restore,
complete erasure and generic code execution remain outside MCP so the agent cannot expand its own
authority or bypass vault safety boundaries.

## Contract analysis

| Boundary | Implementation evidence | Result |
| --- | --- | --- |
| Installation model | Strict Pydantic contracts allow bounded JSON/HTML declarations or allowlisted native references inside versioned provider/pack documents; manifests cannot carry code, module paths, headers or credentials | Converged |
| Persistence | `job_provider_configurations` is user-owned, uniquely keyed, compare-and-swap revisioned and cascades with vault deletion | Converged |
| Network containment | HTTPS/default-port origins only; credentials, redirects, ambient proxies, localhost, `.local`, private literals, mixed/private DNS answers and oversized responses are rejected | Converged |
| Untrusted output | Parsed nodes/items, strings, totals and dates are bounded; non-finite JSON, private/local output links and malformed application email addresses are discarded or rejected | Converged |
| Credential handling | Every configured header value is confidential, redacted from reads and logs, preserved only through an explicit sentinel and stripped from portable exports | Converged |
| Search integration | The composition root contains only the local Vault source; each run adds enabled owned installations after the user is known, while deduplication, failure isolation, cancellation and local-model receipt gates remain authoritative | Converged |
| Provider testing | UI and MCP use the same one-request tester, with bounded samples, private/no-store API responses and the ordinary public-network policy | Converged |
| UI authoring | The responsive English/Italian workspace exposes an honest empty state, file import, bundled-pack import, explicit activation and advanced declarative request/extraction controls | Converged |
| Agent capability | The 41-tool catalog and MCP registration share one scope matrix; provider pack discovery/import/state operations and the complete provider-to-application workflow are typed tools | Converged |
| Authorization | Twelve revocable scopes filter tool discovery and every invocation revalidates the token, principal and exclusive vault lease | Converged |
| Evidence | Search through MCP still uses the mandatory local analysis pipeline; generated resumes/dossiers remain fact-linked and existing readiness/publication checks remain in force | Converged |
| Portability | Archive v7 includes declarative/native installations and pack provenance, strips configured headers and disables every provider on restore; v1–v6 remain supported | Converged |
| Public contracts | Constitution 1.4.0, specification, plan, tasks, data model, OpenAPI, architecture, privacy and README describe the same zero-provider/import model | Converged |

## Adversarial review

The initial implementation was tightened in six places during convergence. All declaration
headers are now treated as secrets instead of relying on a name heuristic. DNS resolution rejects
the entire destination when any answer is non-public, closing mixed-answer and rebinding paths.
URLs and email addresses returned by an untrusted provider are validated before persistence, so a
public feed cannot inject a loopback application link. Provider updates expire the SQLAlchemy
identity map after bulk compare-and-swap writes, preventing stale configuration reads. Native
adapter IDs pass through explicit factory branches rather than dynamic imports, and pack imports
validate every entry and key conflict before a single row commits.

The MCP review split the facade and registration modules by domain, then derived discovery from one
tool catalog. Tool annotations distinguish read-only, mutating, destructive and network operations.
Read-only grants still expose only read tools, partial grants cannot call hidden operations, and a
revoked, expired or changed grant fails on the next call. The stdio server takes the same exclusive
vault lease as the desktop and exposes no generic filesystem, SQL, prompt, grant, restore or erasure
escape hatch.

Migration convergence found one metadata mismatch: the user/enabled lookup index existed in the
Alembic revision but not the ORM table declaration. The model now declares the same index. Native
request/extraction fields use real SQL NULL semantics so the database shape constraint rejects
hybrid rows. `alembic check` passes, and historical archive fixtures remove the v7 provider table
when emulating formats v1–v6.

## Verification result

- Backend: 2,221 passed and 17 expected skips in the complete suite.
- Focused provider configuration: 29 passed, including migration, zero-bootstrap, native allowlist,
  atomic pack import and registry activation; native/declarative portability passed separately.
- MCP: the operational workflow imports the Swiss pack disabled, revision-enables Job-Room and then
  continues through provider validation, job capture and an `applied` application.
- Frontend: 81 Vitest files and 482 tests passed; Node preflight, license/icon checks and ESLint pass.
- Production renderer: Vite built 237 modules and the bundle budget passed at 430,983 B raw /
  136,077 B gzip for the initial load; the largest locale is 25,990 B gzip.
- Static and contracts: Ruff, mypy, OpenAPI, Alembic head/autogenerate and `git diff --check` pass.
- Hygiene: `git diff --check` passed and no test-started MCP or application service remained active.

The workstation now uses checksum-verified Node 24.18.1 ARM64 and npm 11.16.0 from a per-user
side-by-side installation. It is first in the user PATH, frontend dependencies were rebuilt for
ARM64, and every npm command passed the repository engine preflight. The older 24.16.0 runtime was
left in place because unrelated active MCP processes hold it open.

## Residual boundaries

Declarative adapters intentionally do not execute user JavaScript, arbitrary Python, browser
automation or provider-supplied redirects. Providers needing interactive authentication or custom
signing still require a reviewed built-in adapter or a future constrained extension contract.

CareerOS prepares materials and tracks application state but does not silently submit external
forms. Any future submission capability must add destination-specific confirmation, evidence and
anti-CSRF rules rather than treating a stored application URL as authority.

Portable ZIPs remain unencrypted and unsigned. Header stripping and restore-time disabling prevent
credential replay and surprise network access, but users must still protect the archive contents.
Release publication remains subject to protected CI, supported Node and packaged cross-platform
smoke tests on the exact integrated commit.
