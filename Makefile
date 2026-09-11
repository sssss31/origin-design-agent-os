# Developer entry points. Run from origin-design-agent-os/.
API=apps/api
WEB=apps/web
PY=$(API)/.venv/bin/python
PIP=$(API)/.venv/bin/pip

.PHONY: security seed load-test help setup api-install web-install migrate migration api web worker test test-unit lint typecheck fmt check compose-up compose-down keys bootstrap-admin export-schemas

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: api-install web-install ## Create the API venv and install web deps

api-install: ## Install API dependencies into apps/api/.venv
	python3 -m venv $(API)/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -e "$(API)[dev,openai]"

web-install: ## Install web dependencies
	cd $(WEB) && npm install

migrate: ## Apply database migrations
	cd $(API) && .venv/bin/python -m alembic upgrade head

migration: ## Autogenerate a migration: make migration m="add agents"
	cd $(API) && .venv/bin/python -m alembic revision --autogenerate -m "$(m)"

api: ## Run the API with reload on :8000
	cd $(API) && .venv/bin/uvicorn app.main:app --reload --port 8000

worker: ## Run the queue worker (QUEUE_BACKEND=redis)
	cd $(API) && .venv/bin/python -m app.workers.main

web: ## Run the web app on :3000
	cd $(WEB) && npm run dev

test: ## Run all API tests (needs TEST_DATABASE_URL or the default local Postgres)
	cd $(API) && .venv/bin/python -m pytest -q

test-unit: ## Run API unit tests only (no database)
	cd $(API) && .venv/bin/python -m pytest -q tests/unit

lint: ## Lint API + web
	cd $(API) && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd $(WEB) && npm run lint

typecheck: ## Type-check API + web
	cd $(API) && .venv/bin/mypy app
	cd $(WEB) && npx tsc --noEmit

fmt: ## Format API code
	cd $(API) && .venv/bin/ruff format . && .venv/bin/ruff check --fix .

security: ## bandit + pip-audit + npm audit
	cd $(API) && .venv/bin/bandit -q -r app -ll && .venv/bin/pip-audit -r requirements.lock.txt --progress-spinner off
	cd $(WEB) && npm audit --audit-level=high

seed: ## Seed the eight design agents: make seed email=admin@origin.local provider=echo
	cd $(API) && .venv/bin/python -m app.cli seed-design-agents --email $(email) --provider-type $(or $(provider),openai)

load-test: ## SSE load test: make load-test conversation=<id> email=... password=...
	cd $(API) && .venv/bin/python ../../scripts/load_test_sse.py --email $(email) --password $(password) --conversation $(conversation)

check: lint typecheck test security ## Everything CI runs

export-schemas: ## Regenerate packages/shared-schemas from the API domain models
	cd $(API) && .venv/bin/python scripts/export_schemas.py

keys: ## Print fresh JWT_SECRET / ENCRYPTION_KEY
	cd $(API) && .venv/bin/python -m app.cli generate-keys

bootstrap-admin: ## Create the first admin interactively
	cd $(API) && .venv/bin/python -m app.cli bootstrap-admin

compose-up: ## Full stack in Docker
	docker compose -f infra/docker-compose.yml --env-file .env up --build

compose-down:
	docker compose -f infra/docker-compose.yml --env-file .env down
