# Rapporto di convergenza

## Protocollo seguito

Il lavoro ha mantenuto la separazione richiesta:

- Codex ha svolto audit, specifica, piano, test di accettazione, lettura dei diff e gate;
- Gemini 3.8 Flash High, pilotato tramite Antigravity CLI, ha implementato il codice di produzione;
- Codex ha verificato ogni tranche con test indipendenti e ha restituito ad Antigravity soltanto
  difetti riproducibili e criteri di accettazione;
- il controllo finale aggiuntivo è stato affidato a Luna in sola lettura, come autorizzato dal
  proprietario, senza delegargli modifiche.

La CLI Antigravity era già installata (versione 1.2.7), quindi non è stata reinstallata. Al termine
la configurazione locale risultava identica al valore iniziale e non sono state aggiunte workspace
fidate o integrazioni persistenti.

Il piano iniziale preferiva una sola conversazione Antigravity. Sono state mantenute conversazioni
separate per le correzioni emerse dal collaudo reale, così da evitare di perdere il contesto della
sessione principale e da conservare richieste di fix ristrette e verificabili. Questa è una
divergenza procedurale, non funzionale; tutte le modifiche di produzione sono comunque passate da
Antigravity e sono state poi testate da Codex.

## Cicli di implementazione e verifica

1. **Parser e preview** — policy ZIP/XLSX fail-closed, fingerprint, riconciliazione, parser vacancy e
   tracker sanificato. I test sintetici hanno stabilito i confini prima della persistenza.
2. **Persistenza atomica** — modelli, migrazione, planner deterministico, publication journal,
   idempotenza e verifica del grafo account-scoped.
3. **API e interfaccia** — preview/import autenticati, lista/dettaglio/contesto/download, selezione
   ZIP nativa o browser, filtri, materiali e localizzazione EN/IT.
4. **Portabilità e lifecycle** — formato v8 con compatibilità v1-v7, restore validato, reset,
   erasure, cancellazione account e downgrade non distruttivo.
5. **Migrazione reale** — builder allowlist-only, validatore aggregate-only e prova end-to-end in un
   vault temporaneo.

## Correzioni guidate dalla campagna reale

Il collaudo reale e l'audit Luna conclusivo hanno trovato cinque discrepanze di confine che le
fixture iniziali non rendevano evidenti:

1. due file direttamente sotto `application-packets/` potevano essere associati a una candidatura
   per un prefisso simile; il parser ora collega soltanto i file sotto una directory dossier;
2. tredici valori sorgente della piattaforma superavano il campo snapshot di 40 caratteri (massimo
   osservato 67); la proiezione snapshot è ora limitata, mentre il valore sorgente completo resta
   nel record campagna;
3. un valore tracker valido era lungo 4.085 caratteri; l'arbitrario limite portabile di 4.000 è
   stato sostituito con l'esatto limite di cella XLSX, 32.767, e 32.768 viene rifiutato sia
   all'import sia nella portabilità;
4. un archivio composto da una sola directory radice consentita poteva essere scambiato per un
   wrapper; `assets/` e `application-packets/` vengono ora preservate, mentre un wrapper esterno
   continua a essere rimosso;
5. celle numeriche o booleane in colonne testuali potevano raggiungere `.strip()` o `len()` come
   primitivi; le proiezioni sono ora stringhe sicure, mentre il record grezzo conserva tipo e valore
   e le stringhe non vuote mantengono anche gli spazi originali.

Per ogni correzione Codex ha prima aggiunto o eseguito una regressione di confine, Antigravity ha
modificato la produzione, e Codex ha rieseguito suite mirate e suite di area. Nessuna correzione ha
troncato o riscritto il dato sorgente.

Il secondo passaggio read-only di Luna ha verificato la chiusura di tutti i finding e non ha
segnalato blocker residui su privacy, path, atomicità, ownership, contenuti inerti, portabilità,
lifecycle o line budget.

## Prova end-to-end

La prova su vault, database e archivio temporanei ha verificato:

- primo import creato con 177 candidature logiche e 906 artefatti;
- 176 righe tracker, 123 dossier, 122 match, 54 tracker-only e un dossier-only;
- tre righe di credenziali omesse e nessun valore di credenziale persistito;
- secondo import identico restituito come no-op;
- export, inspect e restore del formato v8 con payload e file identici;
- reset ed erasure completi;
- archivio sorgente ricostruito senza modificare la sorgente.

I commitment SHA-256 del collaudo sono registrati come evidenza non sensibile in
`validation.md`. Il percorso sorgente, i nomi dei file e ogni contenuto personale restano fuori dal
repository e dalla documentazione.

## Esito

La convergenza funzionale è raggiunta: i conteggi reali corrispondono all'oracolo, il replay è
idempotente, la portabilità è esatta e il lifecycle non lascia dati esclusivi. Gli esiti completi
dei gate e dell'audit finale sono consolidati in `validation.md`.
