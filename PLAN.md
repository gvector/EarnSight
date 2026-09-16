# EarnSight — Piano di Progetto

Analisi di cedolini paga (PDF) via OCR, estrazione strutturata, visualizzazione,
prospetti/analisi e chatbot LLM con knowledge base fiscale e logica agentica.

> Stato: progettazione — nessun codice funzionale ancora scritto.

---

## 1. Panoramica

Web app che permette di:
1. Caricare cedolini paga (PDF) italiani.
2. Estrarre i dati con OCR **locale** (PaddleOCR/DocTR) + parser a regole (fallback LLM).
3. Visualizzare il cedolino e produrre analisi/prospetti (deterministico + agente analyst).
4. Interagire con un **chatbot agentico** (skill/tool + RAG + fonti ufficiali).

Avvio **monoutente**, architettura già pronta per il **SaaS multi-utente**.

## 2. Architettura del sistema

```
                          [Browser]
                             │ REST
                     [Frontend — Streamlit]          (Docker)
                             │ REST
                      [API — FastAPI] ───────────── [Postgres + pgvector]
                             │ enqueue (Redis)
                      [Worker — Celery]
                        │        │
             ┌──────────┘        └──────────────┐
             ▼                                  ▼
   [OCR Service — PaddleOCR/DocTR]      [Agent Orchestrator]
        (Docker, locale)                 ├─ skills/tool
                                         │    · query_storico
                                         │    · confronta_mesi
                                         │    · cerca_fiscale (RAG)
                                         │    · calcola
                                         │    · spiega_voce
                                         ├─ LLM Gateway (pluggable)
                                         │    ├─ OpenAI  (esterno)
                                         │    └─ Ollama  (locale)
                                         └─ Anonimizzazione PII
```

### Servizi (Docker Compose)

| Servizio | Ruolo | Note |
|----------|-------|------|
| `frontend` | UI Streamlit | upload, tabelle, grafici, chat |
| `api` | FastAPI (REST) | CRUD, orchestratore, gateway LLM, anonimizzazione |
| `worker` | Celery | job asincroni: OCR, estrazione, ingestione RAG |
| `ocr` | PaddleOCR/DocTR | servizio HTTP locale PDF→testo+layout |
| `postgres` | DB relazionale + pgvector | dati estratti, documenti RAG, utenti |
| `redis` | broker/cache | coda Celery |

### Pipeline di elaborazione

1. **Upload** PDF → salvato su volume (`/data/pdfs`, S3 in futuro).
2. **Job asincrono** → `worker` invoca `ocr` (PDF → testo con layout).
3. **Estrazione** → parser locale a regole; LLM solo come fallback su casi ambigui.
   Output: JSON strutturato validato contro schema Pydantic.
4. **Persistenza** → Postgres (JSONB + tabella `payslip_entry` per analytics).
5. **Frontend** → tabella cedolino, prospetti, alert (via query engine condiviso).
6. **Chat agentica** → domanda → orchestratore sceglie skill → query storico/RAG →
   anonimizzazione PII → provider LLM → re-identificazione risposta.

## 3. Stack tecnologico

- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic
- **Frontend**: Streamlit
- **Task**: Celery + Redis
- **OCR**: PaddleOCR / DocTR (Docker dedicato)
- **LLM**: gateway pluggable — OpenAI (GPT-4o/mini) e Ollama (locale); scelta provider lato utente con API key
- **Agente**: orchestratore leggero (ReAct / function-calling) con skill registry;
  degradazione a prompting vincolato su modelli locali deboli
- **RAG**: pgvector, chunking + embedding, retrieval ibrido keyword+vettoriale
- **Anonimizzazione**: rilevamento PII (regex CF, NER, regole) → placeholder → re-identificazione
- **Infra**: Docker + Docker Compose (deploy successivo su hosting)

## 4. Struttura delle cartelle

```
EarnSight/
├── PLAN.md
├── README.md
├── docker-compose.yml
├── .env.example
├── Makefile
├── frontend/                  # UI Streamlit
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── components/            # tabella cedolino, grafici
│   └── pages/                 # upload, cedolino, analisi, chat, impostazioni
├── backend/                   # API FastAPI + worker
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/
│   └── app/
│       ├── main.py
│       ├── api/routes/        # payslips, chat, settings, documents
│       ├── core/              # config, security, logging
│       ├── db/                # session, engine
│       ├── models/            # ORM
│       ├── schemas/           # Pydantic (payslip, chat, ecc.)
│       ├── services/
│       │   ├── extraction/    # parser a regole + fallback LLM
│       │   ├── analytics/     # query engine condiviso (UI + agente)
│       │   ├── agent/         # orchestratore, ciclo ReAct
│       │   ├── skills/        # query_storico, confronta_mesi, cerca_fiscale, calcola, spiega_voce
│       │   ├── llm/           # gateway OpenAI/Ollama
│       │   ├── anonymization/ # PII detection + masking
│       │   └── rag/           # ingestione, retrieval
│       └── workers/           # task Celery
├── ocr-service/               # OCR dedicato
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
├── tests/
├── docs/                      # note, esempi schema, fonti fiscali
├── scripts/                   # seed, ingestione, utility
└── data/                      # volumi (pdfs, documenti RAG) — ignorato da git
```

## 5. Fasi di sviluppo

### Fase 0 — Setup & Scaffolding
- Struttura repo, `docker-compose.yml`, `.env.example`, Makefile
- Dockerfile base per ogni servizio, healthcheck
- Schema DB iniziale (Alembic), avvio stack vuoto funzionante

**Criterio**: `docker compose up` porta su tutti i servizi; API risponde a `/health`.

### Fase 1 — Core Parsing (OCR + Estrazione)
- OCR service PaddleOCR/DocTR: endpoint PDF→testo+layout
- Schema JSON cedolino + validazione Pydantic
- Parser a regole (anagrafica, importi, voci, fiscali/previdenziali, ferie/permessi/TFR)
- **Self-check** LLM single-shot: "i campi sono coerenti col documento?" → confidenza
- Fallback LLM solo sulle voci a bassa confidenza (no loop multi-step)
- Job Celery + endpoint upload/status + persistenza Postgres

**Criterio**: un PDF reale → JSON validato con campi attesi e voci corrette.

### Fase 2 — UI Streamlit
- Pagina upload, stato elaborazione
- Tabella cedolino (competenze/trattenute), dettaglio voci
- Pagina impostazioni (provider LLM, API key)

**Criterio**: caricamento e visualizzazione completa di un cedolino da browser.

### Fase 3 — Analytics & Prospetti (+ Analyst agent)
- **Query engine condiviso** (layer tipizzato: `get_net_by_month`, `sum_field`, `compare`, ...)
- Core deterministico: trend storico, confronto mensile, proiezioni annuali, quadro fiscale, alert/anomalie
- **Analyst agent**: usa lo stesso query engine per domande esplorative in linguaggio naturale

**Criterio**: con più cedolini, grafici e alert corretti; l'agente risponde a domande aperte sui dati.

### Fase 4 — LLM Chat Agentica + RAG + Anonimizzazione
- Gateway LLM pluggable (OpenAI/Ollama)
- **Skill registry** + ciclo agentico (ReAct / function-calling): `query_storico`, `confronta_mesi`, `cerca_fiscale`, `calcola`, `spiega_voce`
- Anonimizzazione PII → provider → re-identificazione (bypassata con Ollama locale)
- RAG fiscale: ingestione documenti curati + fonti ufficiali, retrieval ibrido
- UI chat (Q&A sui dati, spiegazione voci, consigli fiscali)

**Criterio**: la chat, posta una domanda, ricerca autonomamente nello storico e nella KB e risponde senza esporre PII al provider esterno.

## 6. Privacy & sicurezza

- OCR ed estrazione: **solo locali**.
- Chat verso provider esterno: **anonimizzazione PII** (CF, nomi, azienda → placeholder) + re-identificazione.
- Data access layer tipizzato: l'agente invoca funzioni/endpoint, **mai SQL libero** sui dati sensibili.
- Con Ollama locale: nessun dato esce dalla macchina.
- Segreti (API key) solo via `.env`, mai nel repo.
- Predisposizione multi-tenant (FK `user_id`) fin da subito.

## 7. Decisioni & note

- Provider LLM scelto **dall'utente** via impostazioni (OpenAI o Ollama).
- Estrazione: deterministica; LLM solo per self-check e fallback mirato (no agente).
- Agente: pieno valore in chat (skill/tool) e analisi (insight aperti); **degradazione a prompting vincolato** su modelli locali deboli.
- Materiali reali (cedolini + documenti fiscali) forniti dall'utente per tarare parser e RAG.
- Deploy iniziale locale (Docker Compose), poi hosting remoto.
