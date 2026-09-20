# Local migration quickstart

1. Build a deterministic ZIP from the campaign root with the feature script. The script includes
   only the documented allowlist and never includes the CareerOS repository, backups, outputs,
   temporary files or standalone credential stores. The ZIP does contain the original tracker,
   which may carry a credentials worksheet: treat it as sensitive, keep it outside the repository
   and delete it after the verified import. CareerOS stores only a deterministic credentials-free
   tracker derivative.
2. Open CareerOS → Applications → Import campaign.
3. Select the ZIP and review the fingerprint, counts, reconciliation and omission warnings.
4. If no profile exists, confirm a profile display name. This creates only a minimal profile;
   imported facts remain review candidates.
5. Confirm import. Search/filter the resulting cards and open one to inspect original metadata and
   download historical materials.
6. Use native CareerOS controls to update stage/tasks, prepare dossier/CV/letter/email, export files,
   open the original posting and record external submission. CareerOS never sends automatically.
7. Create and inspect a portable backup before removing the source campaign directory.

For release validation, use a disposable vault and the aggregate oracle in `validation.md`; never
point automated destructive lifecycle tests at the active user vault.
