# Specification: Dossier Vacancy Metadata

## Context

A real dossier-only `vacancy.md` uses `# Vacancy record — APP-...` and bullet metadata
such as `- **Company:**` and `- **Role:**`. The importer currently projects its title as
the placeholder heading and its company as `Unknown company`, although both facts are
present in the source. This harms review and deduplication without changing application
eligibility.

## Requirements

- Parse ordinary plain, bold, and bulleted `Role`/`Title`, `Company`, `Location`,
  `Category`, and URL labels without inventing absent fields.
- Propagate an explicitly parsed location, category, and posting URL into the
  dossier-only application; do not silently discard them after parsing or
  mislabel the posting URL as a direct application URL. Existing URL safety
  normalization remains in the import planner.
- For an `APP-...` vacancy-record placeholder H1, use an explicit role label if present.
  Preserve ordinary role H1 headings when no explicit replacement is needed.
- Keep output deterministic and inert. Do not contact a provider, infer eligibility,
  alter grants, or change database schema.
- Existing imports are not silently rewritten; any repair must use an authorized,
  revision-checked application service operation.

## Acceptance

Fictional parser and importer tests confirm the bulleted case, the ordinary headings,
metadata propagation, and absent-value fallbacks. A local existing record may be corrected only from verified
source facts, preserving stage and source-linked review history.
