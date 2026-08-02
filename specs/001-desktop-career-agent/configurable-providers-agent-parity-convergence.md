# Configurable providers and agent-operation parity — convergence

Date: 2026-08-02

Decision: the constitution, specification, plan, tasks, data model, OpenAPI contract,
implementation, tests and owner documentation now use one explicit provider-installation model and one typed
scope-to-tool catalog. An authorized agent can carry out the ordinary provider, search, career,
resume, job and application workflow without gaining generic access to the vault or the ability to
expand its own grant.

| Area | Converged behavior | Result |
| --- | --- | --- |
| Bootstrap | The local Vault source is the only initial source; no network provider row or adapter exists until explicit configuration/import | Converged |
| Provider format | Revisioned JSON/HTML declarations plus versioned data-only provider/pack imports; native references use a closed reviewed factory | Converged |
| Authoring | Responsive bilingual UI with honest empty state, JSON file/Swiss-pack import, explicit activation and advanced request/extraction controls | Converged |
| Validation | UI, REST and MCP share strict schemas, selector validation and redacted diagnostics | Converged |
| Network | Public HTTPS only, exact-origin request paths, no redirects/proxies, fresh all-public DNS checks and bounded retries/responses | Converged |
| Secrets | All configured headers are write-only, redacted, omitted from archives and never restored as enabled credentials | Converged |
| Runtime registry | Each search adds only enabled owned installations to the local source; every imported Swiss native or declarative source remains dormant otherwise | Converged |
| Local evidence | Search analysis remains mandatory, local and receipt-verified before claims are exposed | Converged |
| Agent scopes | Twelve revocable scopes filter a shared 41-tool catalog and are revalidated on every call | Converged |
| Agent workflow | Typed operations cover provider pack discovery/import/state, Career Vault, jobs, search, resumes, dossiers, applications, events and follow-up tasks | Converged |
| Authority boundary | No arbitrary SQL/files/code, grant management, restore, complete erasure or credential reads | Converged |
| Concurrency | Provider and ordinary domain mutations preserve existing expected-revision checks and user ownership | Converged |
| Portability | v7 round-trips declarations without headers and disabled; historical v1–v6 archives remain supported | Converged |
| Erasure | Complete Career Vault deletion includes provider declarations and verifies their removal | Converged |
| Migration | Head `b0c1d2e3f4a5`, downgrade/re-upgrade and ORM autogenerate comparison pass | Converged |
| Quality gates | 2,221 backend tests, 482 frontend tests, supported Node preflight, static analysis, lint, build and bundle budget passed locally | Converged locally |

Node 24.18.1 ARM64 is checksum-verified, first in the user PATH and passed every npm engine
preflight. Packaged cross-platform smoke tests and release signing were not run locally.
