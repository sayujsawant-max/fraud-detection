# ============================================================
# FraudShield MLOps — Makefile
# Convenience commands for local dev + Docker orchestration.
# ============================================================

# docker compose looks for .env next to the compose file by default. Since
# our compose lives in infra/, we point it explicitly at the project-root .env
# so ${POSTGRES_USER} etc. interpolations resolve correctly.
COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env

.PHONY: help setup dev test lint format docker-up docker-down docker-build logs clean

help:
	@echo "FraudShield MLOps — available commands:"
	@echo "  make setup         Install backend + frontend dependencies locally"
	@echo "  make dev           Run the FastAPI backend locally with reload"
	@echo "  make test          Run backend test suite (pytest)"
	@echo "  make lint          Run ruff linter on backend"
	@echo "  make format        Run ruff formatter on backend"
	@echo "  make docker-up     Start all 7 services via Docker Compose"
	@echo "  make docker-down   Stop all services"
	@echo "  make docker-build  Rebuild all Docker images"
	@echo "  make logs          Tail Docker Compose logs"
	@echo "  make clean         Remove caches and build artifacts"

setup:
	cd backend && python -m pip install --upgrade pip && pip install -r requirements.txt -r requirements-dev.txt
	cd frontend && npm install

dev:
	cd backend && uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	cd backend && pytest tests/ -v --tb=short

lint:
	cd backend && ruff check src tests

format:
	cd backend && ruff format src tests

docker-up:
	$(COMPOSE) up --build -d

docker-down:
	$(COMPOSE) down

docker-build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f

clean:
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/**/__pycache__ backend/__pycache__
	rm -rf frontend/.next frontend/node_modules/.cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
