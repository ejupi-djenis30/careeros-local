# Handoff finale: Campaign Workspace

## Stato

La feature 003 è implementata sul branch `codex/003-campaign-workspace`. La campagna storica può
essere assemblata in un ZIP deterministico, visualizzata in preview, importata una sola volta per
fingerprint, gestita con i workflow CareerOS, esportata/ripristinata e cancellata integralmente.

Non sono stati eseguiti commit, push o modifiche alla sorgente della campagna. Nessun dato reale è
stato aggiunto al repository.

## Punti di ingresso operativi

- Builder: `scripts/build_campaign_archive.py`
- Validazione aggregata: `backend/campaigns/aggregate_validation.py`
- Parser/import: `backend/campaigns/`
- API: `backend/api/routes/campaigns.py`
- UI: pagina Applications e componenti `CampaignImportPanel`, `CampaignPreview`,
  `CampaignFilters`, `CampaignMaterials`
- Portabilità: formato archivio v8 sotto `backend/portability/`
- Migrazione DB: revisione Alembic `c0a1b2c3d4e5`

## Uso previsto

1. Costruire localmente l'archivio dalla sorgente con il builder allowlist-only.
2. In Applications, selezionare il ZIP e controllare la preview aggregata.
3. Confermare esplicitamente l'import legato al fingerprint mostrato.
4. Lavorare sulle candidature con ricerca, filtri, dettaglio, materiali, stage, eventi, task e
   workflow di preparazione CareerOS.
5. Conservare o trasferire il vault con export v8; usare inspect prima del restore.

Il ZIP contiene ancora il tracker sorgente e deve essere trattato come materiale sensibile. Dopo
un import verificato va eliminato secondo la policy locale. Nel vault viene conservato soltanto il
derivato tracker senza foglio o stringhe di credenziali.

## Invarianti di manutenzione

- Preview senza side effect; import atomico, account-scoped e idempotente.
- Nessuna credenziale, telemetria, AI remota o dipendenza di rete.
- Materiali sempre inerti e scaricati come allegati dopo verifica di digest e ownership.
- Nessun invio, email, pubblicazione o conferma di fatti durante l'import.
- Compatibilità portabile v1-v7 preservata; campagne incluse da v8.
- Downgrade rifiutato in presenza di righe campagna.
- Moduli Python sotto 300 linee e componenti React sotto 150, salvo eccezione costituzionale
  documentata prima del codice.

## Evidenza di accettazione

Il vault temporaneo reale ha raggiunto esattamente 177 candidature e 906 artefatti, ha omesso tre
righe di credenziali, ha reso il secondo import un no-op e ha superato export/inspect/restore,
reset ed erasure. Conteggi, test, gate e digest non sensibili sono riportati in `validation.md`; la
motivazione e le correzioni di convergenza sono in `analysis.md` e `convergence.md`.
