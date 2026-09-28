# Revisione repo EarnSight — punti correggibili e stato vs PLAN.md

**Data:** 2026-09-23
**Ambito:** intera repo (backend, frontend, infra, test) confrontata con `PLAN.md` e `CONTEXT.md`.
**Metodo:** lettura del codice + verifica empirica delle ipotesi (esecuzione della pipeline e
delle route su PDF sintetici). Ogni punto marcato **[verificato]** è stato riprodotto, non dedotto.

Stato di partenza sano: `ruff check` e `ruff format --check` passano su `backend tests frontend`,
36 test verdi, CI configurata su lint + test + build immagini.

---

## 1. Punti da correggere

### 1.1 — `template` e `raw_text` vengono azzerati ad ogni correzione **[verificato]**

`ExtractionResult.to_jsonb()` (`result.py:151`) persiste solo `fields/entries/issues/validation`:
`template` e `raw_text` non finiscono nel JSONB. `from_jsonb()` (`result.py:95`) li ricostruisce
quindi vuoti, e `apply_to_document()` (`result.py:164-165`) li riscrive sul documento:

```
dopo estrazione:  template='generic'  raw_text=320 char
dopo correzione:  template=None       raw_text=0 char
```

Succede su **ogni** `PATCH /payslips/{id}/fields` e `POST /{id}/llm-resolve`, che fanno esattamente
`from_jsonb → apply_* → apply_to_document`.

**Perché conta:** `llm-resolve` costruisce il prompt con `doc.raw_text` (`payslips.py:158`). Quindi
correggere un campo a mano *svuota il testo* e il successivo "Risolvi con LLM" parte con un prompt
senza documento — cioè il fallback LLM previsto dal piano smette di funzionare proprio nel flusso
"prima correggo, poi chiedo all'LLM". In UI spariscono anche "Testo estratto" e il template.

**Fix:** includere `template` e `raw_text` nella proiezione JSONB (e nel `from_jsonb`), oppure
rendere `apply_to_document` non distruttivo quando il risultato non porta quei valori.
⚠️ `tests/test_pipeline.py::test_to_jsonb_from_jsonb_roundtrip` **asserisce** la shape monca
(`assert set(data) == {"fields","entries","issues","validation"}`): va aggiornato col fix, è il
motivo per cui il bug non è mai stato visto.

### 1.2 — Correzione con valore non numerico → 500 **[verificato]**

`CorrectionIn.fields` è `dict[str, float | str | int | None]` (`schemas/payslip.py:60`): una
`PATCH {"fields": {"period_month": "marzo"}}` è valida per lo schema, poi `run_validation` fa
`1 <= month <= 12` e alza `TypeError: '<=' not supported between instances of 'int' and 'str'`,
non intercettato → 500. Il frontend converte i tipi, ma l'API non deve dipendere dal client.

**Fix:** tipizzare/validare i campi attesi in `CorrectionIn` (coercizione per `period_*` e campi
numerici) e restituire 422.

### 1.3 — Risposta LLM malformata → 500 invece di 502

In `llm_resolve_fields` le conversioni `int(value)` / `float(value)` (`payslips.py:168,170`) stanno
**fuori** dal `try` che protegge la chiamata al provider: se il modello risponde `"2.250,00"` o un
testo, `ValueError` non gestita → 500. Stesso tema del punto precedente: il confine con l'esterno
(utente e LLM) non è tipizzato.

### 1.4 — Frontend: importo col punto decimale corrotto in silenzio

`review.py:21` fa `raw.replace(".", "").replace(",", ".")`: digitando `2250.50` viene salvato
**225050.0**, senza alcun errore. Contraddice il principio del piano «campi non corretti →
inserimento utente o richiesta LLM, **mai valori silenziosi**».

**Fix:** accettare entrambi i separatori riconoscendo quale è decimale, oppure rifiutare input
ambigui con un messaggio esplicito.

### 1.5 — Frontend: documenti omonimi si nascondono a vicenda

In `documents.py:86` e `review.py:114` le opzioni della selectbox sono un `dict` con chiave
`f"{filename} · {periodo}"`. Due upload dello stesso file per lo stesso periodo collassano in
un'unica voce: **un documento diventa irraggiungibile dalla UI** (caso tutt'altro che raro: si
ricarica lo stesso cedolino dopo un errore).

**Fix:** usare gli id come opzioni con `format_func` per l'etichetta.

### 1.6 — Isolamento multi-utente: i documenti "orfani" sono di tutti

`list_payslips` include `user_id IS NULL` (`payslips.py:87`) e `_get_document` accetta il documento
se `doc.user_id is None` (`payslips.py:32`). Oggi è innocuo (monoutente, l'upload valorizza sempre
`user_id`), ma il piano dichiara predisposizione multi-tenant «fin da subito»: è esattamente il tipo
di scorciatoia che sopravvive fino alla Fase 5 e diventa una fuga di dati fra tenant.

**Fix:** `user_id` NOT NULL + migrazione di backfill, e filtro stretto `user_id == user.id`.

### 1.7 — Default insicuri che non falliscono mai

`secret_key = "dev-secret-change-me"` e `auth_password = "admin"` (`core/config.py`). Un deploy con
`.env` incompleto parte in silenzio con un segreto noto — e poiché la chiave Fernet deriva da
`SECRET_KEY` (`core/crypto.py`), anche le API key "cifrate a riposo" diventano decifrabili da
chiunque conosca il default. Il piano mette l'auth fra i requisiti non negoziabili per l'esposizione
online.

**Fix:** fail-fast all'avvio se `SECRET_KEY` è il default fuori da un flag `DEBUG`/`DEV`.

### 1.8 — Upload senza limiti

`upload_payslip` valida solo l'estensione e fa `content = await file.read()` (tutto in RAM). Per
un'app raggiungibile online servono un limite di dimensione e un controllo dei magic bytes `%PDF`.

### 1.9 — Alembic è presente ma fuori dal giro

`main.py:24` esegue `Base.metadata.create_all` ad ogni avvio; `docker-compose.yml` non lancia mai
`alembic upgrade`; e `0001_initial` è a sua volta un `create_all` (quindi non è uno snapshot DDL
storico, ma "qualunque cosa dicano i modelli oggi"). Risultato: due sorgenti di verità per lo schema
e, su un DB creato dall'app, `alembic upgrade head` fallisce perché `app_setting` esiste già.
La Fase 0 del piano chiede «Schema DB (Alembic)»: l'artefatto c'è, ma non governa nulla.

**Fix:** togliere `create_all` dal lifespan, far girare le migrazioni all'avvio (o via `make migrate`
nel compose), e rigenerare `0001` come DDL esplicito.

### 1.10 — Il fallback inline di `dispatch_processing` è rotto fuori da Postgres **[verificato]**

`db/session.py:12` costruisce l'URL sincrono con `replace("+asyncpg", "+psycopg")`: con qualsiasi
altro driver async (es. `sqlite+aiosqlite`) la sostituzione non avviene, `SyncSessionLocal` viene
creata **su un driver async** e il fallback inline esplode con un opaco
`sqlalchemy.exc.MissingGreenlet`. I test non lo intercettano perché iniettano sempre una
`session_factory`, cosa che la route non può fare (`payslips.py` chiama `dispatch_processing(doc_id)`
senza factory). Il path «inline quando il broker è giù» documentato in `CONTEXT.md` non è quindi mai
esercitato end-to-end.

**Fix:** derivare l'URL sincrono in modo esplicito per driver (mappa asyncpg→psycopg,
aiosqlite→sqlite) e aggiungere un test che passi dalla route.

### 1.11 — Nessun test sulle route del flusso principale

La suite copre pipeline, parser, validazione, runner e le route `/settings`, ma **non** esiste un
test HTTP su `upload → estrazione → PATCH /fields → llm-resolve`. È il buco che ha lasciato passare
1.1, 1.2 e 1.10 insieme.

---

## 2. Pulizia (nit, nessun impatto funzionale)

| Punto | Dove |
|---|---|
| `LlmUnavailable` definita e mai usata | `services/llm/gateway.py:27` |
| Condizione morta: nessun errore su `total_deductions` esiste mai prima di quel guard | `services/extraction/validation.py:60` |
| `_dispatch_and_refresh` può restituire `None` ma è annotata `PayslipDocument` | `api/routes/payslips.py` |
| Import locali dentro `get_gateway_for_user` senza motivo di ciclo | `services/llm/gateway.py` |
| `make lint` copre `backend tests`, la CI anche `frontend` → il check locale passa e la CI può fallire | `Makefile` vs `.github/workflows/ci.yml` |
| Sqlite di test mai rimossi (6 accumulati, gitignorati ma sporcano la working dir): manca teardown | `tests/conftest.py` |
| Provider OpenAI senza API key → errore "Nessun provider LLM configurato (LLM_PROVIDER vuoto)", fuorviante; il frontend abilita il bottone guardando solo `llm_provider` | `payslips.py` + `pages/review.py` |
| `api`, `worker` e `frontend` non hanno healthcheck (solo postgres e redis), mentre la Fase 0 li prevede per ogni servizio | `docker-compose.yml` |

---

## 3. Stato dell'implementazione rispetto a PLAN.md

| Fase | Stato | Dettaglio |
|---|---|---|
| **0 — Setup & scaffolding** | ✅ quasi completa | Compose, Dockerfile, CI (lint+test+build), Makefile, auth JWT singolo utente: fatti. Mancano: healthcheck su api/worker/frontend; Alembic non operativo (§1.9). |
| **1 — Core parsing** | 🟡 nucleo fatto, 3 scoperti | Fatti: estrazione PyMuPDF testo+coordinate, router digitale/scan (`needs_ocr`), schema tipizzato `ExtractionResult`, validazione aritmetica deterministica, correzione utente **o** LLM mirato, job Celery + fallback inline, persistenza Postgres (JSONB + `payslip_entry`). Mancano: **parser per-template** (vedi sotto), **validazione incrociata CU↔cedolini**, **taratura sui ~30 PDF reali**. |
| **2 — UI Streamlit** | ✅ completa | Login modale, upload multiplo con stato, dettaglio cedolino, pagina revisione, impostazioni con API key cifrata. Restano i due difetti UI §1.4 e §1.5. `frontend/components/` è ancora vuoto (i componenti vivono in `lib/ui.py`: va bene, ma la cartella del piano è inutilizzata). |
| **3 — Analytics & prospetti** | ⬜ non iniziata | `services/analytics/` contiene solo `__init__.py`. Nessun query engine condiviso, nessun grafico/alert. |
| **4 — Chat agentica + RAG** | ⬜ non iniziata | `services/agent/`, `skills/`, `rag/`, `anonymization/` vuoti. **Anticipato:** il gateway LLM pluggable (Ollama/OpenAI, key cifrata) è già in piedi dalla Fase 1. pgvector è nell'immagine Postgres ma non usato. |
| **5 — Backlog** | ⬜ non iniziata | `ocr-service/` vuoto, nessun deploy/reverse proxy. README portfolio: fatto (anticipato). |

### Scostamenti da segnalare esplicitamente

1. **Template detection senza parser per-template.** `detect_template()` riconosce
   `zucchetti`/`teamsystem` (`templates.py`) ma `parse_payslip()` è un unico parser generico
   label-based: il template viene salvato e mostrato, però **non cambia il parsing**. Il piano
   (Fase 1) prevede «parser a regole per-template + fallback generic». Il seam c'è, manca il
   consumatore — da chiudere quando arrivano i PDF reali dei due software paghe.
2. **CU supportata solo come etichetta.** `doc_type` accetta `"cu"` (unico punto del backend che la
   cita), ma non esiste né un parser CU né la validazione incrociata «quadro CU coerente con la
   somma dei cedolini» che il piano mette fra i criteri di uscita della Fase 1.
3. **Criterio di uscita Fase 1 non ancora dimostrabile.** Il criterio è sui «~30 PDF reali»: oggi i
   test girano solo su PDF sintetici generati in `conftest.py`. Finché non si tarano parser e
   template sui documenti veri, la Fase 1 resta formalmente aperta.

---

## 4. Ordine di intervento suggerito

1. **§1.1** (correzione che svuota `raw_text`) — rompe il flusso centrale del piano, fix piccolo.
2. **§1.2 + §1.3** (500 su input utente/LLM) — tipizzare il confine, stessa sessione di lavoro.
3. **§1.4 + §1.5** (difetti UI: corruzione silenziosa e documenti irraggiungibili).
4. **§1.11** (test HTTP sul flusso upload→correzione) — chiude la classe di bug di cui sopra.
5. **§1.9 + §1.10** (Alembic e URL sincrono) — debito infrastrutturale, da saldare prima del deploy.
6. **§1.6 + §1.7 + §1.8** (isolamento, segreti, limiti upload) — prima di esporre l'app online.
7. Scostamenti di piano: parser per-template e CU, quando arrivano i documenti reali.
