# Comandi del progetto.
# Python sempre via $(PY) -m …: non dipende dal PATH né dagli script del venv.
PY ?= .venv/bin/python
PY_PATHS = backend tests scripts frontend/e2e
E2E = docker compose -p earnsight-e2e -f docker-compose.yml -f docker-compose.e2e.yml

.PHONY: setup up down logs ps migrate test lint fmt check fe-check e2e lock privacy-check

# --- prima installazione (venv Python 3.14 + dipendenze front-end) -------------------
# --clear: ricrea un .venv esistente (es. uno ancora su Python 3.12)
setup:
	uv venv --clear --python 3.14 .venv
	uv pip install --python $(PY) -r backend/requirements.txt -r backend/requirements-dev.txt
	cd frontend && npm ci

# --- stack Docker -------------------------------------------------------------------
# --wait: ritorna solo quando tutti i servizi sono healthy (o fallisce subito)
up:
	docker compose up -d --build --wait --wait-timeout 300

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

migrate:
	docker compose exec api alembic upgrade head

# --- controlli ----------------------------------------------------------------------
test:
	$(PY) -m pytest -q
	cd frontend && npm test

# stessi controlli della CI: un lint locale verde implica un lint CI verde
lint:
	$(PY) -m ruff check $(PY_PATHS)
	$(PY) -m ruff format --check $(PY_PATHS)
	cd frontend && npm run lint

fmt:
	$(PY) -m ruff format $(PY_PATHS)
	$(PY) -m ruff check --fix $(PY_PATHS)

# front-end: tipi, lint, test unitari e build di produzione (come la CI)
fe-check:
	cd frontend && npm run typecheck && npm run lint && npm test && npm run build

# tutto ciò che non richiede Docker, prima di un commit
check: lint test fe-check privacy-check

# end-to-end: stack Docker usa-e-getta (nginx → api → worker → postgres), Playwright, poi giù
e2e:
	$(E2E) up -d --build --wait --wait-timeout 300
	cd frontend && E2E_BASE_URL=http://localhost:18080 E2E_PASSWORD=e2e-password-not-for-production npx playwright test; \
		status=$$?; cd .. && $(E2E) down -v; exit $$status

# nessun valore dei cedolini reali (example_ced/) nei file che andrebbero in git
privacy-check:
	$(PY) scripts/check_no_real_data.py

# Lock delle dipendenze Python: si modificano i .in, poi `make lock` rigenera i .txt.
# Python 3.14 come Dockerfile e CI; dev vincolato al lock del backend.
# (Il front-end usa package-lock.json: npm install --save-exact.)
LOCK = uv pip compile --quiet --universal --python-version 3.14
lock:
	$(LOCK) backend/requirements.in -o backend/requirements.txt
	$(LOCK) backend/requirements-dev.in -c backend/requirements.txt -o backend/requirements-dev.txt
