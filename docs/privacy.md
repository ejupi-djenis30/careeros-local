# Privacy

CareerOS Local is designed to minimize disclosure of highly sensitive career data.

## Stored locally

The app may store identity and contact data, work and education history, skills, languages, achievements, goals, preferences, source documents, profile photos, resume drafts and publications, job snapshots, application tasks and dossier versions, coach conversations, and redacted AI execution metadata. Model binaries and partial downloads are stored in separate app-managed directories.

## Not collected

The project contains no product telemetry, advertising identifiers, cloud AI integration, remote prompt logging, or analytics SDK. The application does not silently upload a profile or resume. Job-provider requests are user-initiated search operations and disclose only deterministic queries built from the explicit role, strategy and preferences. Provider planning never invokes the local model, and only v3 cache records marked `deterministic-explicit` can be reused.

The daily application agenda is calculated locally from the authenticated user's scalar role and
next-action projections. It does not read task-event or dossier bodies, contact a calendar service,
or invoke the local model.

## Model context

The local model does not automatically receive the complete vault. Each task selects a bounded evidence set. Retrieved source text is treated as untrusted data, and generated claims must cite selected local identifiers. Execution audits store fingerprints, counts, validation codes, timing, and model identity—not prompts or generated text.

## Control and portability

Users can export a manifest-verified ZIP backup from one consistent database snapshot and restore it into an empty vault. Provider listings may be shared only when their provider identity is stable. Manually captured listings use a one-way, server-derived per-user namespace, ignore client-supplied manual ids, and are never merged across users. Shared provider rows exclude user-specific discovery queries, while restore rejects private or stale cross-user collisions instead of silently merging them.

The exact confirmation phrase erases profile, resume, search, match, application, workflow, coaching, learned-preference, and AI-audit data plus app-owned files. SQLite secure deletion, WAL checkpoints, and vacuuming reduce recoverable database remnants; user-scoped staged-file cleanup is retryable if an operating-system error interrupts it. Managed model/runtime files can be removed in the same operation. Backup files are not encrypted by the application; store them in an encrypted location if confidentiality is required.

## Operating-system protections

The app inherits the current user account’s filesystem permissions. Enable full-disk encryption, lock the device, restrict backup access, and remove old installers or archives from shared folders. Uninstalling an application may not remove user data on every platform; use in-app erasure first when disposal is intended.
