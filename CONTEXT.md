# CONTEXT.md — Lingua del dominio EarnSight

I termini qui definiti sono i nomi canonici di concetti, module e seam del
progetto. Usarli (e aggiungerli qui quando nasce un concetto nuovo) mantiene
il codice e le conversazioni allineati al dominio.

## Concetti di dominio

- **Cedolino** — busta paga italiana mensile in PDF; l'input principale dell'app.
- **CU (Certificazione Unica)** — certificazione annuale dei redditi; secondo tipo
  di documento supportato, utile per validazione incrociata con i cedolini.
- **Document** — un file caricato (cedolino o CU) con il suo stato di elaborazione;
  modello ORM `PayslipDocument`.
- **Entry** — una voce di paga riconosciuta nel cedolino (spettanza o trattenuta),
  con codice, descrizione e importo.
- **Field** — un campo canonico estratto (es. `net_pay`, `period_month`), con
  provenienza e confidenza.
- **Issue** — un problema rilevato dalla validazione, con azione suggerita:
  `user` (correzione manuale) oppure `llm` (richiesta mirata al gateway).
- **Validation** — i controlli aritmetici deterministici (netto+trattenute=lordo,
  somma voci vs totali, periodo valido). Prima linea di difesa, prima dell'LLM.
- **Template** — la firma di layout di un software paghe; guida il parser.

## Terminologia architetturale

- **ExtractionResult** — il contratto tipizzato del risultato dell'estrazione
  (`backend/app/services/extraction/result.py`): fields, entries, issues,
  validation, status. Unica interface consumata da pipeline, worker, API e
  (in Fase 2) frontend.
- **FieldProvenance** — la shape di un Field: value, confidence, source, corrected.
- **from_document** — la ricostruzione completa del risultato dal Document:
  JSONB (fields/entries/issues/validation) + colonne dedicate (template,
  raw_text, doc_type). Le route di correzione passano sempre da qui, così
  template e raw_text sopravvivono a ogni PATCH.
- **coerce_correction_value** — la coercizione tipizzata delle correzioni
  (utente e LLM): INT_FIELDS interi, NUMERIC_FIELDS finiti; ValueError →
  422 (input utente) o skip con warning (risposta LLM malformata).
- **sync_database_url** — la derivazione dell'URL sync dal DATABASE_URL
  (asyncpg→psycopg, aiosqlite→pysqlite), unica per worker, session sync e
  Alembic; i driver sconosciuti falliscono all'avvio con un errore chiaro.
- **TEMPLATE_PARSERS** — il registry che collega detect_template al parser
  per-template (`parser.py`): il pipeline sceglie da qui, fallback generico.
- **parse_cu** — il parser CU (label-based, quadro lavoro dipendente):
  compenso lordo, ritenute, netto, anno; la validazione per la CU controlla
  solo l'anno, non il mese.
- **DocumentStatus** — il ciclo di vita di un Document: pending, processing,
  done, needs_review, needs_ocr, failed.
- **apply_to_document** — la seam di proiezione del risultato sul Document
  (JSONB, colonne dedicate, status): un solo owner, condivisa da worker e API.
- **dispatch_processing** — la seam che possiede la decisione di esecuzione del
  job (`app/workers/dispatch.py`): task Celery quando il broker è raggiungibile,
  thread locale quando non lo è. Due adapter giustificano il seam.
- **Gateway LLM** — adapter pluggable verso Ollama (locale, primario) o OpenAI
  (quando deployato online). Due adapter giustificano il seam.

## Limiti notevoli

- OCR: i PDF senza layer di testo diventano `needs_ocr`; l'OCR è componente futura.
- Nessun SQL libero sui dati sensibili: l'agente (Fase 4) invoca funzioni tipizzate.
