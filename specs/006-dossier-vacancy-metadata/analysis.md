# Analysis: Dossier Vacancy Metadata

## Requirement coverage

| Requirement | Evidence |
| --- | --- |
| Read plain, bold, and bulleted metadata | Fictional parser and end-to-end archive parser tests cover plain labels, bold labels, bulleted bold labels, category, location, URL, and absent fields. |
| Placeholder heading fallback | `Vacancy record — APP-...` uses the explicit `Role` when present; ordinary H1 remains authoritative. |
| Deterministic, offline, no fabricated metadata | The parser only reads text in the supplied Markdown. No provider or database access was added to parsing. Absent fields keep existing unknown/null defaults. |
| Preserve historical imports | No migration or batch rewrite. The single local Two Spice record was corrected from the source packet and current employer-linked URL through `ApplicationService.update_preparation(expected_revision=3)`. Owner-scoped `campaign show` confirmed revision 4, `preparing`, and the pre-existing `hold` review. |

## Checks run

- Targeted parser tests: 11 passed.
- Campaign test group: 171 passed.
- Ruff on all changed Python source and tests: passed.
- Mypy on all changed Python source files: passed.
- `git diff --check`: passed.
- Full backend regression: 2,812 passed, 17 skipped, 1 pytest-cache warning in 924.96 seconds.

The known pytest cache write warning is a local permissions issue on `.pytest_cache`, not a test failure.
