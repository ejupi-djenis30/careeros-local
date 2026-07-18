# Privacy

CareerOS Local is designed to minimize disclosure of highly sensitive career data.

## Stored locally

The app may store identity and contact data, work and education history, skills, languages, achievements, goals, preferences, source documents, profile photos, resume drafts and publications, job snapshots, applications, coach conversations, and redacted AI execution metadata. Model binaries and partial downloads are stored in separate app-managed directories.

## Not collected

The project contains no product telemetry, advertising identifiers, cloud AI integration, remote prompt logging, or analytics SDK. The application does not silently upload a profile or resume. Job-provider requests are user-initiated search operations and disclose only the search parameters required by that provider.

## Model context

The local model does not automatically receive the complete vault. Each task selects a bounded evidence set. Retrieved source text is treated as untrusted data, and generated claims must cite selected local identifiers. Execution audits store fingerprints, counts, validation codes, timing, and model identity—not prompts or generated text.

## Control and portability

Users can export a manifest-verified ZIP backup, restore it into an empty vault, and erase profile data plus managed model/runtime files using an exact confirmation phrase. Backup files are not encrypted by the application; store them in an encrypted location if confidentiality is required.

## Operating-system protections

The app inherits the current user account’s filesystem permissions. Enable full-disk encryption, lock the device, restrict backup access, and remove old installers or archives from shared folders. Uninstalling an application may not remove user data on every platform; use in-app erasure first when disposal is intended.
