# EarnSight

[![CI](https://github.com/gvector/EarnSight/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/gvector/EarnSight/actions/workflows/ci.yml)

Analisi di cedolini paga italiani in PDF: carichi i documenti, EarnSight ne estrae i
dati, controlla che i conti tornino e ti mostra quanto hai ricevuto mese per mese. I
campi che non tornano si correggono a mano o con un LLM a scelta (anche locale).
L'elaborazione avviene sul tuo computer.

**Stack:** Python 3.12, FastAPI, Celery, PostgreSQL, PyMuPDF · React, TypeScript, nginx ·
Docker Compose.

## Avvio

Serve Docker.

```bash
cp .env.example .env    # imposta SECRET_KEY e AUTH_PASSWORD
make up                 # avvia tutti i servizi
open http://localhost:8080
```

Test: `make setup` (una volta), poi `make check`.
