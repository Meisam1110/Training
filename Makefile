.DEFAULT_GOAL := help
PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
.PHONY: help install test lint run demo build up down migrate

help:  ## list targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-9s %s\n",$$1,$$2}'

install:  ## create .venv and install backend (dev) + frontend deps
	python3 -m venv .venv
	.venv/bin/pip install -q -e "backend[dev,postgres]"
	@if [ -f frontend/package-lock.json ]; then cd frontend && npm ci --no-audit --no-fund; fi

test:  ## backend tests (tests/core + tests/integrations, one run) with coverage
	cd backend && ../$(PY) -m pytest tests/core tests/integrations --durations=5 --cov=app --cov-report=term-missing:skip-covered

lint:  ## ruff
	cd backend && ../$(PY) -m ruff check .

migrate:  ## apply migrations to $$DATABASE_URL (default sqlite dev db)
	cd backend && ../$(PY) -m alembic upgrade head

run: migrate  ## dev server on http://127.0.0.1:8000 (dev key is generated in backend/data)
	cd backend && TMS_AUTO_MIGRATE=1 ../$(PY) -m uvicorn app.main:app --reload --port 8000

demo:  ## load SYNTHETIC demo data (prints demo logins once), then run
	cd backend && ../$(PY) -m app.demo --reset
	$(MAKE) run

build:  ## build the single image (frontend + API)
	docker build -t tms:latest .

up:  ## start app + postgres (needs .env, see .env.example)
	docker compose up -d --build

down:  ## stop the stack (volumes are kept)
	docker compose down
