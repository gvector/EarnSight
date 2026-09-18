# EarnSight — Piano di Progetto

Analisi di cedolini paga (PDF) italiani: estrazione strutturata, visualizzazione,
prospetti/analisi e chatbot LLM con knowledge base fiscale e logica agentica.

> Stato: **Fase 0 + Fase 1 in implementazione** (estrazione testuale + validazione + API).
>
> Progetto orientato al **portfolio**, ma pensato per essere raggiungibile online
> (deploy su VPS con dominio, login singolo utente).

---

## 1. Panoramica

Web app che permette di:
1. Caricare cedolini paga (PDF) e Certificazioni Uniche (CU) italiane.
2. Estrarre i dati con **estrazione testuale** (PyMuPDF — i PDF sono digitali) e
   parser a regole per-template; **OCR solo come fallback futuro** per PDF scannerizzati.
3. **Validare** l'estrazione con controlli aritmetici deterministici; i campi non
   corretti vengono **corretti dall'utente** o richiesti a un **LLM** (fallback mirato).
4. Visualizzare il cedolino e produrre analisi/prospetti (deterministico + agente analyst).
5. Interagire con un **chatbot agentico** (skill/tool + RAG + fonti ufficiali).

Avvio **monoutente con login**, architettura già pronta per il **SaaS multi-utente**.

## 2. Architettura del sistema

```
                          [Browser]
                             │ REST
                     [Frontend — Streamlit]          (Docker)
                             │ REST
                      [API — FastAPI] ───────────── [Postgres + pgvector]
                             │ enqueue (Redis)
                      [Worker — Celery]
                        │                 │
             ┌──────────┘                 └────────────┐
             ▼                                        ▼
   [Estrazione testuale (in-worker)]           [Agent Orchestrator]
    PyMuPDF → template detection               ├─ skills/tool
    → parser a regole → validazione            │    · query_storico
    → correzioni utente / fallback LLM         │    · confronta_mesi
                                               │    · cerca_fiscale (RAG)
   [OCR Service — futuro, solo scan]           │    · calcola
                                               │    · spiega_voce
                                               ├─ LLM Gateway (pluggable)
                                               │    ├─ Ollama  (locale — primario)
                                               │    └─ OpenAI  (esterno — quando online)
                                               └─ Anonimizzazione PII (solo path OpenAI)
```

### Servizi (Docker Compose)

| Servizio | Ruolo | Note |
|----------|-------|------|
| `frontend` | UI Streamlit | login, upload, tabelle, grafici, chat |
| `api` | FastAPI (REST) | auth, CRUD, orchestratore, gateway LLM |
| `worker` | Celery | job asincroni: estrazione, ingestione RAG |
| `postgres` | DB relazionale + pgvector | dati estratti, documenti RAG, utenti |
| `redis` | broker/cache | coda Celery |
| `ocr` | *(futuro)* PaddleOCR/DocTR | solo per PDF scannerizzati, fuori scope attuale |

### Pipeline di elaborazione

1. **Upload** PDF → salvato su volume (`/data/pdfs`, S3 in futuro).
2. **Job asincrono** (Celery) → estrazione.
3. **Router input**: il PDF ha layer di testo? (pdf digitali: sì) → estrazione testuale
   PyMuPDF (parole + coordinate per layout); altrimenti → stato `needs_ocr` (futuro).
4. **Template detection** per firma del layout (software paghe) → parser a regole
   per-template con fallback generic label-based. Output: JSON strutturato (Pydantic).
5. **Validazione aritmetica deterministica** (primaria):
   netto + trattenute = lordo, somma voci vs totali, periodo valido, quadro CU
   coerente con la somma dei cedolini.
6. **Revisione**: i campi con problemi vengono **inseriti/corretti dall'utente**
   (API/UI) oppure **richiesti all'LLM** (fallback mirato, solo su quei campi).
7. **Persistenza** → Postgres (JSONB + tabella `payslip_entry` per analytics).
8. **Frontend** → tabella cedolino, prospetti, alert (via query engine condiviso).
9. **Chat agentica** → domanda → orchestratore sceglie skill → query storico/RAG →
   anonimizzazione PII → provider LLM → re-identificazione risposta (solo path OpenAI).

## 3. Stack tecnologico

- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic
- **Estrazione**: PyMuPDF (fitz) — testo + coordinate; pdfplumber come alternativa
- **OCR (futuro)**: PaddleOCR / DocTR (servizio dedicato, solo per scan)
- **Frontend**: Streamlit
- **Auth**: login singolo utente (JWT bearer, password con scrypt)
- **Task**: Celery + Redis
- **LLM**: gateway pluggable — **Ollama locale come primario**, **OpenAI quando
  l'app è online/deployata** (VPS economico non regge modelli locali decenti);
  scelta provider lato utente con API key (cifrata a riposo, Fernet)
- **Agente**: orchestratore leggero (ReAct / function-calling) con skill registry;
  degradazione a prompting vincolato su modelli locali deboli
- **RAG**: pgvector, chunking + embedding, retrieval ibrido keyword+vettoriale
- **Anonimizzazione**: rilevamento PII (regex CF, NER, regole) → placeholder →
  re-identificazione; necessaria solo per il path OpenAI
- **Infra**: Docker + Docker Compose; deploy su VPS con reverse proxy (HTTPS)

## 4. Struttura delle cartelle

```
EarnSight/
├── PLAN.md
├── README.md
├── pyproject.toml               # config ruff + pytest
├── docker-compose.yml
├── .env.example
├── Makefile
├── .github/workflows/ci.yml     # lint + test + build immagini
├── frontend/                    # UI Streamlit
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── components/              # tabella cedolino, grafici
│   └── pages/                   # login, upload, cedolino, analisi, chat, impostazioni
├── backend/                     # API FastAPI + worker
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/
│   └── app/
│       ├── main.py
│       ├── api/routes/          # auth, payslips, chat, settings, documents
│       ├── core/                # config, security, logging
│       ├── db/                  # session, engine
│       ├── models/              # ORM
│       ├── schemas/             # Pydantic (payslip, chat, ecc.)
│       ├── services/
│       │   ├── extraction/      # text layer, template detection, parser, validazione
│       │   ├── analytics/       # query engine condiviso (UI + agente)
│       │   ├── agent/           # orchestratore, ciclo ReAct
│       │   ├── skills/          # query_storico, confronta_mesi, cerca_fiscale, calcola, spiega_voce
│       │   ├── llm/             # gateway Ollama/OpenAI
│       │   ├── anonymization/   # PII detection + masking
│       │   └── rag/             # ingestione, retrieval
│       └── workers/             # task Celery
├── ocr-service/                 # (futuro) OCR per PDF scannerizzati
├── tests/                       # test unitari pipeline (PDF sintetici)
├── docs/                        # note, esempi schema, fonti fiscali
├── scripts/                     # seed, ingestione, utility
└── data/                        # volumi (pdfs, documenti RAG) — ignorato da git
```

## 5. Fasi di sviluppo

### Fase 0 — Setup & Scaffolding
- Struttura repo, `docker-compose.yml`, `.env.example`, Makefile, CI GitHub Actions
- Dockerfile per ogni servizio, healthcheck
- Schema DB (Alembic), auth singolo utente (login JWT), avvio stack funzionante

**Criterio**: `docker compose up` porta su tutti i servizi; API risponde a `/health`;
login funziona.

### Fase 1 — Core Parsing (estrazione testuale + validazione)
- Estrazione testo+layout con PyMuPDF; router digitale/scan (`needs_ocr` per scan)
- Schema JSON cedolino/CU + validazione Pydantic
- Template detection per firma layout (2 software paghe reali dell'utente, ~30 sample)
- Parser a regole per-template + fallback generic label-based
- **Validazione aritmetica deterministica** come self-check primario:
  netto+trattenute=lordo, somma voci vs totali, periodo valido, quadro CU vs cedolini
- **Revisione campi non corretti**: correzione utente via API/UI **oppure** richiesta
  mirata all'LLM (solo campi con problemi; il self-check LLM non può correggere errori
  OCR a monte — non vede il PDF originale — quindi resta secondario)
- Job Celery + endpoint upload/status/corrections + persistenza Postgres

**Criterio**: i ~30 PDF reali → JSON validato con campi attesi e voci corrette;
check aritmetici passano; quadro CU compatibile con la somma dei cedolini.

### Fase 2 — UI Streamlit
- Pagina login (JWT)
- Pagina upload, stato elaborazione
- Tabella cedolino (competenze/trattenute), dettaglio voci
- **Pagina revisione**: campi segnalati dalla validazione → inserimento manuale
  o richiesta LLM con un click
- Pagina impostazioni (provider LLM, API key — cifrata a riposo con Fernet)

**Criterio**: login, caricamento, visualizzazione e correzione completa di un
cedolino da browser.

### Fase 3 — Analytics & Prospetti (+ Analyst agent)
- **Query engine condiviso** (layer tipizzato: `get_net_by_month`, `sum_field`, `compare`, ...)
- Core deterministico — **scope descrittivo**: trend storico, confronto mensile,
  quadro fiscale, alert/anomalie. Solo dati presenti nei documenti, nessun calcolo
  fiscale nuovo.
- **Analyst agent**: usa lo stesso query engine per domande esplorative in linguaggio naturale

**Criterio**: con più cedolini, grafici e alert corretti; l'agente risponde a domande
aperte sui dati.

### Fase 4 — LLM Chat Agentica + RAG + Anonimizzazione
- Gateway LLM pluggable (Ollama primario / OpenAI per il deploy online)
- **Skill registry** + ciclo agentico (ReAct / function-calling): `query_storico`,
  `confronta_mesi`, `cerca_fiscale`, `calcola`, `spiega_voce`
- Anonimizzazione PII → provider → re-identificazione **solo per il path OpenAI**
  (con Ollama locale nessun dato esce dalla macchina)
- RAG fiscale: ingestione documenti curati + fonti ufficiali, retrieval ibrido
- UI chat (Q&A sui dati, spiegazione voci, consigli fiscali con disclaimer)

**Criterio**: la chat, posta una domanda, ricerca autonomamente nello storico e
nella KB e risponde senza esporre PII al provider esterno.

### Fase 5 — Backlog (post-MVP)
- Proiezioni fiscali (TFR, annuale) con KB fiscale validata e versionata
- OCR per PDF scannerizzati (servizio dedicato)
- Multi-utente completo (SaaS)
- Deploy VPS con dominio, reverse proxy HTTPS
- Materiali portfolio: README, screenshot, seed dati sintetici

## 6. Privacy & sicurezza

- Estrazione: **solo locale** (PyMuPDF in-worker).
- Chat verso OpenAI: **anonimizzazione PII** (CF, nomi, azienda → placeholder) +
  re-identificazione. Con Ollama locale: nessun dato esce dalla macchina.
- **Login obbligatorio** (singolo utente, JWT): un'app di dati paga esposta online
  senza auth non è proponibile.
- API key salvate da UI: **cifrate a riposo** (Fernet, key da env), mai in chiaro nel DB.
- Data access layer tipizzato: l'agente invoca funzioni/endpoint, **mai SQL libero**
  sui dati sensibili.
- Segreti (API key, SECRET_KEY, credenziali) solo via `.env`, mai nel repo.
- Deploy online dietro reverse proxy con **HTTPS**.
- Predisposizione multi-tenant (FK `user_id`) fin da subito.

## 7. Decisioni & note

- **Progetto da portfolio**, raggiungibile online su VPS; qualità del codice e
  CI trattate come parte del prodotto.
- **LLM ibrido**: Ollama in locale (primario), OpenAI quando deployato online
  (i VPS economici non reggono modelli locali decenti). Gateway pluggable.
- Estrazione: **PDF digitali** → testo primario, OCR solo futuro per scan;
  deterministica; LLM solo per fallback mirato su campi con problemi (no agente).
- Validazione **aritmetica deterministica** primaria: più affidabile del self-check
  LLM, che non vede il PDF originale e non può correggere errori a monte.
- Campi non corretti → **inserimento utente o richiesta LLM**, mai valori silenziosi.
- Scope Fase 3 = solo dati presenti nei documenti; proiezioni fiscali rinviate a
  Fase 5 con KB validata.
- Materiali reali (~30 cedolini + CU, 2 software paghe) forniti dall'utente per
  tarare parser e template detection.
- CU (Certificazione Unica) supportata come tipo documento; utile per validazione
  incrociata con i cedolini.
