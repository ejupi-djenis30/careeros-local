# Feature Specification: Headless Campaign CLI

**Feature branch**: `codex/job-search-2026-09-20`
**Status**: Implemented and validated
**Constitution**: CareerOS Local Constitution 2.0.1

## Problem

The campaign workspace can be previewed and imported through the desktop HTTP workflow, but an
owner who deliberately keeps the desktop application closed cannot perform the same operation from
the supported `careeros` command line. This blocks local automation even though the campaign parser,
fingerprint confirmation, atomic importer, migration backup, and owner-scoped read models already
exist.

## User outcomes

### US1 - Preview an archive without mutation (P1)

As the local vault owner, I can run `careeros campaign preview ARCHIVE` and receive the bounded,
credential-free campaign preview as JSON without opening or mutating the vault.

Acceptance scenarios:

1. A valid archive returns its fingerprint, aggregate counts, warnings, and profile requirement.
2. Invalid or unreadable input returns a stable redacted error and a non-zero exit code.
3. Preview never starts a writable vault session.

### US2 - Import into one explicitly named local account (P1)

As the local vault owner, I can import the exact previewed archive while the desktop is closed by
naming the destination account, repeating the preview fingerprint, and acknowledging the local
write.

Acceptance scenarios:

1. Import requires `--username`, `--expected-fingerprint`, and
   `--acknowledge-local-vault-write`.
2. The CLI acquires the existing exclusive desktop lease, migrates with the normal backup path,
   resolves exactly one account, and delegates to the existing atomic campaign importer.
3. A missing account, changed archive, busy desktop, or failed import returns a stable redacted
   error without partial persistence.
4. Re-importing the same fingerprint is idempotent.

### US3 - Verify the imported campaign headlessly (P1)

As the local vault owner, I can list campaigns for the explicitly named account and inspect one
campaign's owner-scoped detail as JSON without the desktop UI.

The persisted `summary.status_counts` describes the imported tracker snapshot, not current
application stages. List and detail responses must label that scope explicitly. Detail responses
must also include owner-scoped live stage counts across the whole campaign, independent of query,
stage, priority, and pagination filters, so an operator can distinguish import history from the
current pipeline after recording submissions.

## Security and privacy constraints

- The command is an offline local-vault maintenance boundary; it never starts the HTTP server,
  launches a browser, or sends data externally.
- The destination account must be named explicitly. No default, first-user, or all-user behavior is
  allowed.
- Import requires an exact SHA-256 fingerprint confirmation plus a separate write acknowledgement.
- The existing archive allowlist, credential-sheet omission, transaction, ownership, and asset
  integrity checks remain authoritative and are not reimplemented in the CLI.
- Unexpected exceptions are redacted through the existing CLI error boundary.

## Out of scope

- Submitting applications, sending messages, or uploading documents to employers.
- Editing campaign records through the CLI.
- Cloud AI, browser automation, or a second writable vault process.
