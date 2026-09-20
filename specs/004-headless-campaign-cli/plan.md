# Implementation Plan: Headless Campaign CLI

1. Add a `campaign` command group to `backend.automation.cli` with `preview`, `import`, `list`, and
   `show` subcommands.
2. Keep preview side-effect free. Use `build_campaign_preview` directly from archive bytes.
3. Run import through `automation_runtime(..., migrate=True, write_access=True)`, require the
   explicit write acknowledgement, resolve the exact username, and call `import_campaign` with the
   confirmed fingerprint.
4. Run list/show through the existing read-only runtime and owner-scoped campaign API service.
5. Convert expected campaign/input failures to stable `AutomationRuntimeError` codes so paths,
   credentials, and tracebacks cannot escape.
6. Add parser, dispatch, preview, import, owner-scope, and redaction tests using fictional data.
7. Run focused tests, formatting/type/security checks, then the repository release gates required
   by `AGENTS.md`.

No schema change is required; the feature uses the existing campaign migration and models.
