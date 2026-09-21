# Validation Quickstart

Use repository .venv Python 3.12, Node >=24.18 <25 and Rust. Configure the application settings
instance and test database in OS temp; remove DATA_DIR/DATABASE_URL environment overrides after
settings bootstrap so tests constructing fresh Settings() retain their expected defaults.
Never use the user's Career directory or real vault. Packaging needs a supported Python whose
architecture matches the target; the current .venv is x64, while the installed Rust target is ARM64.
No commit, push, release or user-account configuration is required.

1. Seed a fictional profile with confirmed facts and explicit preferences using existing test
   factories. Start the local backend/renderer with no local model configured.
2. In Agent Access create a grant with context:read and proposals:write after disclosure and
   password confirmation. Copy the token only deliberately into the MCP child environment.
3. Use the UI-generated installed Codex or Claude Code stdio configuration with the actual
   bundled console launcher, --connection-file and --acknowledge-agent-disclosure. Explicit
   developer tests may use --desktop-url at the current canonical loopback /api/v1 base.
4. Create discover/analyze work in Agent Workspace. Through an actual MCP client initialize,
   list tools, list requests, fetch context and submit the contract fixture with its digest.
5. Review in the app. Reject one proposal and accept another; repeat acceptance and verify one
   existing application timeline. Change an input and confirm stale acceptance is blocked.
6. Select each of the nine presets, preview, change layout preserving fixture text, publish
   PDF/DOCX. Inspect all text/page bounds and representative images of each layout/letter.
7. Request materials, submit a cited proposal, edit/accept drafts, export packet. Reopen the
   ZIP, verify manifest hashes and letter/CV content and email attachments. State remains unsent.
8. Revoke the grant and repeat reads/writes; both fail. Exercise cancel/expiry/foreign IDs,
   request conflicts, oversized bodies, hostile advert text and mid-acceptance rollback.
9. Import fictional profile/narrative/goal Markdown; review candidates and confirm source
   file hashes unchanged. Test backup/restore and reset with new records.

Commands from repository root (use .venv/Scripts executables on Windows):
- ruff check backend tests/backend
- mypy backend --ignore-missing-imports --no-error-summary
- pytest tests/backend -q
- In frontend: npm test, npm run lint, npm run build, npm run test:e2e
- In frontend/src-tauri: cargo fmt --check; cargo clippy --all-targets -- -D warnings; cargo test
- Alembic on temporary database: upgrade head; downgrade -1; upgrade head

Targeted suites under tests/backend/agent_work, automation, resumes, applications and portability
and associated UI tests must precede full gates. Actual command output belongs in OS temp;
summarize status/counts in validation.md. Record limitations, failures and skipped release gates.
