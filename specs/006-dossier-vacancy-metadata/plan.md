# Plan: Dossier Vacancy Metadata

Constitution 2.0.1 reviewed; no amendment is needed. Extend only the deterministic
`backend/campaigns/vacancy_parser.py` metadata recognition and preserve its parsed
location, category, and posting URL in the dossier-only import mapping. Keep the parser's existing
return schema and URL safety normalization. Add fictional regression tests before local-vault
verification. Do not reimport the historical campaign to repair one record; use the
existing `ApplicationService.update_preparation` with an exact revision and verified
employer-linked posting, then reread the owner-scoped campaign projection.
