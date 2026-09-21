# Validation: Headless Campaign CLI

Validation evidence will record:

- parser/help coverage and missing-acknowledgement refusal;
- preview parity with the existing campaign preview service;
- exact fingerprint binding and idempotent import behavior;
- explicit account ownership for list/detail reads;
- redacted errors for missing files, unknown accounts, invalid archives, and importer failures;
- focused pytest results plus the full repository gates required by `AGENTS.md`;
- aggregate-only results from the real closed-vault import (campaign/application/artifact counts,
  never credential values).

## Evidence — 20 September 2026

- Focused CLI tests: 20 passed.
- Full backend suite: 2,791 passed and 17 skipped; the only warning was the pre-existing Windows
  access denial for pytest's optional `.pytest_cache` write.
- Ruff: passed for `backend`, `tests/backend`, and the campaign material generator.
- Mypy: passed for `backend` after an explicit cast at the third-party FastMCP return boundary.
- Frontend: 616 Vitest tests plus 13 Node contract/license/icon tests passed; ESLint and the
  production Vite bundle passed.
- Rust: `cargo fmt --check`, clippy with warnings denied, 28 tests, and doc tests passed.
- Alembic: upgrade to head, downgrade one revision, and re-upgrade passed on a disposable SQLite
  database.
- Archive preview: fingerprint
  `b47f19b0a7f167a8400fe0d24e630da85b575ca603b0ba8f14d1e3e8f5078f41`; 197 logical
  applications, 196 tracker rows, 143 dossiers, 1,051 artifacts, and 3 credential rows omitted.
- Closed-vault import into the explicitly named `djenis123` account created campaign
  `7b34996d-76df-5bcf-ac37-2932f800c03a` with 197 applications, 1,051 artifacts, 111 tasks,
  four source documents, and one warning.
- Repeating the exact fingerprint-bound import returned the same campaign with `created: false`.
- Owner-scoped `campaign show --query APP-20260920` returned exactly the 20 new application IDs.
- PDF QA: 40 of 40 PDFs are one-page A4 documents with selectable text; every page was rendered
  with Poppler and visually reviewed in five contact sheets.
