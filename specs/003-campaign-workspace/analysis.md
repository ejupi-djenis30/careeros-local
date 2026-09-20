# Analisi conclusiva della campagna

## Scopo e metodo

La campagna è stata analizzata in sola lettura e descritta tramite conteggi, tipi e digest. Nessun
nome di persona o azienda, contatto, nota, corpo di documento o valore di credenziale è stato
copiato in codice, fixture, log o documentazione. I test automatici usano esclusivamente campagne
fittizie; la campagna reale è stata verificata in un vault temporaneo separato.

L'analisi ha coperto il tracker XLSX, i dossier per candidatura, i riferimenti radice, gli asset, i
template e gli script ammessi dalla policy. Sono stati esclusi output derivati, backup, directory
temporanee, repository applicativi annidati e qualsiasi radice non riconosciuta.

## Inventario aggregato verificato

| Elemento | Risultato |
|---|---:|
| righe del tracker | 176 |
| colonne del tracker | 28 |
| dossier | 123 |
| tracker/dossier riconciliati | 122 |
| record solo tracker | 54 |
| record solo dossier | 1 |
| candidature logiche | 177 |
| artefatti consentiti | 906 |
| byte di input | 95.222.414 |
| righe credenziali omesse | 3 |
| credenziali importate | 0 |

La distribuzione storica è 78 `Applied`, 85 `Closed`, 5 `Saved` e 8 `Preparing`. Diciannove dossier
usano un suffisso descrittivo dopo l'identificatore: la riconciliazione conserva il nome completo
come provenienza ma collega il dossier alla candidatura corretta. Due file collocati direttamente
alla radice di `application-packets/` restano materiali della campagna e non vengono attribuiti a
una candidatura per somiglianza del nome.

## Traduzione delle attività in CareerOS

| Attività della campagna precedente | Rappresentazione locale | Operazione disponibile in CareerOS |
|---|---|---|
| censire una candidatura | campagna, `Job`, `Application` e collegamento sorgente | apertura, ricerca e filtro per campagna |
| conservare tutti i campi del tracker | record originale inerte più proiezioni tipizzate | consultazione del contesto della candidatura |
| seguire stato e cronologia | stage conservativo ed eventi immutabili | cambio stage tramite i controlli applicativi esistenti |
| ricordare il prossimo passo | task pendente solo per record attivi con azione | agenda, completamento e nuova pianificazione |
| preparare CV, dossier, lettera ed email | workflow CareerOS nativi più evidenze storiche | generazione/modifica/esportazione dai dati confermati |
| consultare vacancy e pacchetto storico | artefatti raggruppati per categoria | download autenticato come allegato inerte |
| conservare fonti di profilo, obiettivi e storytelling | `SourceDocument` revisionabili con ruolo esplicito | revisione prima di confermare fatti o preferenze |
| trovare candidature per priorità, stage o testo | proiezioni indicizzate e filtri UI | ricerca per ID, titolo, azienda, piattaforma e categoria |
| aprire l'annuncio o registrare un invio | URL e metadati della candidatura | apertura controllata e conferma esplicita di un invio esterno |
| archiviare o trasferire l'intero workspace | formato portabile v8 | export, ispezione, restore, reset ed erasure |

L'import non invia candidature o email, non esegue script o HTML, non pubblica documenti e non
conferma automaticamente fatti del profilo. Queste rimangono azioni esplicite del proprietario.
`Closed` viene mappato ad `archived`, senza dedurre un rifiuto; stato ed esito originali restano
consultabili.

## Modello e flusso dati

1. `scripts/build_campaign_archive.py` costruisce un archivio deterministico usando una allowlist.
2. Preview e parser applicano limiti al contenitore ZIP e al pacchetto XLSX prima di qualsiasi
   scrittura, calcolano il fingerprint e restituiscono solo aggregati e campioni limitati.
3. Il tracker originale non viene salvato: CareerOS genera una copia XLSX deterministica che
   contiene solo il foglio applicazioni e conserva tutti i 28 campi, inclusi valori lunghi validi
   fino al limite XLSX di 32.767 caratteri.
4. Il piano d'import produce identificatori, proiezioni, eventi e task deterministici. Le stringhe
   destinate a campi CareerOS più stretti sono validate o proiettate senza perdere il valore
   sorgente nel record campagna.
5. Una transazione account-scoped pubblica righe e asset content-addressed; il journal consente di
   convergere dopo esiti di commit incerti. Un secondo import dello stesso fingerprint è un no-op.
6. Le API espongono lista, dettaglio, contesto e download soltanto al proprietario. I download
   verificano path, lunghezza e digest e forzano `attachment`, `nosniff` e `no-store`.
7. Il formato portabile v8 valida relazioni, ordine, path canonici e digest prima del restore. Reset,
   erasure e cancellazione account rimuovono righe e byte esclusivi, preservando i byte ancora
   condivisi.

## Copertura e conclusione

CareerOS locale può ora contenere l'intera campagna ammessa dalla policy e continuare il lavoro da
un unico workspace: 177 candidature, 906 artefatti, tracker completo senza credenziali, materiali,
fonti revisionabili, eventi e task. Le sole esclusioni sono deliberate: segreti, radici non
riconosciute, contenuti temporanei/derivati e automazioni che avrebbero effetti esterni senza una
conferma umana.
