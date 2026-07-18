# CareerOS Local Constitution

<!--
Sync impact report
- Reset: all previous product documentation retired by owner request.
- Version: 1.0.0 (new CareerOS Local baseline).
- Ratified: 2026-07-17.
- Principles: desktop ownership, local intelligence, grounded career truth, durable vault,
  bounded architecture, measurable delivery, secure distribution, accessible documents.
- Dependent artifacts: plan, specification, task and checklist templates reviewed.
-->

## Core Principles

### I. The desktop application is the product

CareerOS Local MUST install, launch, update and uninstall as a native desktop application
without requiring Docker, a shell, Python, Node.js or a manually started web server. All
application services MUST bind only to loopback, use an ephemeral authenticated session,
and terminate with the desktop process. Windows, macOS and Linux release artifacts MUST
be reproducible from source and published with checksums.

Rationale: a local-first product must feel owned by the user, not operated like a server.

### II. Local-only intelligence is a non-negotiable boundary

Prompts, embeddings, model outputs, profile data and documents MUST never be sent to a
remote inference service. The source tree and dependency graph MUST contain no remote-AI
client or fallback. Model acquisition is an explicit user action; inference works offline
after acquisition. Runtime endpoints MUST be loopback-only and denied by default when
their locality cannot be proven.

Rationale: privacy cannot depend on provider configuration or user vigilance.

### III. Career truth is grounded and reviewable

Every generated claim MUST reference one or more career-fact identifiers. AI MAY select,
compress and rewrite supported facts, but MUST NOT invent employers, dates, credentials,
skills, results or metrics. Structured outputs MUST pass schema, evidence and consistency
validation before persistence. Low-confidence results MUST be surfaced for review instead
of silently accepted.

Rationale: accuracy is more valuable than fluency in high-stakes career material.

### IV. Small-model quality is measured, not assumed

AI workflows MUST be designed for locally runnable small models through bounded context,
task-specific schemas, deterministic retrieval, constrained decoding and selective repair.
Every AI behavior change MUST be evaluated against a versioned offline golden set. Release
gates MUST cover schema validity, evidence coverage, hallucination rate and task accuracy;
latency and memory are recorded by model profile.

Rationale: compact models become dependable through system design and evidence.

### V. The career vault belongs to the user

SQLite and user-selected local files are canonical. Schema migrations MUST be transactional,
backed up when destructive, and tested from both an empty database and the supported prior
version. Users MUST be able to export, import and delete their complete vault in documented,
non-proprietary formats. Application updates MUST preserve data and generated documents.

Rationale: local storage without portability and recovery is only local lock-in.

### VI. Boundaries stay explicit

Desktop lifecycle, transport, use cases, domain rules, persistence, model runtimes, source
connectors and document rendering MUST remain separate. Domain code depends on ports rather
than framework implementations. Route handlers contain no business orchestration. Python
modules SHOULD remain below 300 lines and React components below 150 lines; exceptions MUST
be justified in the feature plan with a decomposition follow-up.

Rationale: the heavy refactor must reduce accidental coupling rather than relocate it.

### VII. Production evidence precedes release

Acceptance criteria MUST be executable. Unit tests cover domain rules; contract tests cover
process and API boundaries; integration tests cover SQLite, migrations, inference and export;
end-to-end tests cover installation, first launch, restart and upgrade. Tests deny network by
default. A release is incomplete if lint, type checks, tests, AI evaluations, packaging, SBOM,
license policy, vulnerability scan or artifact smoke tests fail.

Rationale: production-grade is a verified state, not a label.

### VIII. Safety and accessibility are product behavior

Logs MUST exclude profile bodies, prompts, tokens, document text and contact details. The
desktop shell MUST enforce a restrictive content security policy, disable arbitrary navigation,
validate IPC messages and avoid renderer privileges. Core workflows MUST be keyboard accessible.
ATS resumes MUST be text-extractable and photo-free; visual templates MUST remain readable
without color and strip image metadata. PDF and DOCX exports are generated locally and checked
for required sections, non-empty text and overflow.

Rationale: private data and career documents deserve secure, inclusive defaults.

## Product gates

- No code, package, environment variable or UI path may enable remote AI inference.
- No hidden network request may occur during launch, editing, inference, rendering or tests.
- Job-source access and model download are separate, explicit, auditable capabilities.
- A generated career claim without evidence is rejected before it reaches the user.
- The default installer starts on a clean supported OS without developer tooling.
- The desktop app must recover cleanly from a crashed local model or backend process.
- Release artifacts must be signed where credentials are available; unsigned development
  artifacts must be labeled clearly and must still include checksums and an SBOM.

## Spec-driven workflow

Every substantial change follows this order:

1. specify user outcomes, constraints and independently testable acceptance scenarios;
2. clarify only decisions that materially alter scope or safety;
3. research unknowns using primary sources and record decisions with alternatives;
4. plan architecture, migrations, contracts, packaging and constitution compliance;
5. create dependency-ordered tasks with tests and release evidence;
6. implement in thin, independently verifiable slices;
7. analyze artifact consistency, converge remaining work and rerun every release gate.

## Governance

This constitution supersedes every project-local agent instruction and historical document.
Amendments require a written impact report and semantic version change. Removing or weakening a
privacy, evidence, durability or release gate is a major change; adding a mandatory principle is
minor; clarification without changed obligations is patch. Every plan MUST perform a constitution
check before research and again before release. Exceptions require owner approval, an expiry date
and a tracked remediation task; there are no implicit exceptions.

**Version**: 1.0.0 | **Ratified**: 2026-07-17 | **Last amended**: 2026-07-17
