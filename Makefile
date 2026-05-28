# ============================================================
# FraudShield MLOps — Makefile
# Convenience commands for local dev, Docker orchestration, lint,
# tests, smoke tests, MLflow, drift, retraining, observability.
# ============================================================

# All compose invocations go through this variable so we never have a
# "two flavours of docker-compose" mismatch across targets.
COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env

# Local MLflow URI used by train-mlflow / mlflow-runs / promote-model.
MLFLOW_TRACKING_URI ?= http://localhost:5000

# API port the host should hit. Docker maps host 8001 → container 8000.
# Override with `make smoke-predict API_PORT=8000` when running `make dev`.
API_PORT ?= 8001

# Default backend API URL used by smoke + load scripts.
SMOKE_BASE_URL ?= http://localhost:$(API_PORT)

# Admin API key used by the curl helpers. Override on the CLI.
API_KEY ?= change-me

.PHONY: help \
	setup dev clean \
	docker-up docker-down docker-build docker-ps docker-restart logs \
	test test-backend test-frontend \
	lint lint-backend lint-frontend lint-all \
	format format-backend format-check \
	precommit precommit-install \
	build-frontend dev-frontend \
	db-upgrade db-downgrade db-current init-db \
	generate-data train-baseline train-mlflow mlflow-runs promote-model \
	seed-logs seed-drift drift-check logs-api-test drift-api-test api-test \
	run-monitoring-flow run-retraining-flow deploy-prefect-flows start-prefect-worker \
	retraining-runs trigger-retrain trigger-monitoring trigger-reload phase6-test \
	metrics metrics-test prometheus-targets grafana-url monitoring-smoke phase7-test \
	smoke-health smoke-predict smoke-monitoring smoke-full load-test phase9-test \
	readiness-check phase10-check

# ------------------------------------------------------------------
# Help
# ------------------------------------------------------------------

help:
	@echo "FraudShield MLOps — available commands"
	@echo ""
	@echo "Setup & infra:"
	@echo "  setup                    Install backend + frontend dev dependencies"
	@echo "  docker-up                Start the full Docker Compose stack"
	@echo "  docker-down              Stop all services"
	@echo "  docker-build             Rebuild all images"
	@echo "  docker-ps                Show running services"
	@echo "  docker-restart           Restart all services"
	@echo "  logs                     Tail Docker Compose logs"
	@echo "  clean                    Remove caches + build artifacts"
	@echo ""
	@echo "Local dev:"
	@echo "  dev                      Run FastAPI locally on port 8000 with reload"
	@echo "  dev-frontend             Run Next.js dev server on port 3000"
	@echo ""
	@echo "Tests:"
	@echo "  test                     Backend pytest + coverage (alias for test-backend)"
	@echo "  test-backend             Backend pytest with --cov-fail-under=65"
	@echo "  test-frontend            Frontend build (Next.js compiles + type-checks)"
	@echo ""
	@echo "Lint + format:"
	@echo "  lint                     ruff check + frontend next lint"
	@echo "  lint-backend             ruff check src tests"
	@echo "  lint-frontend            next lint inside frontend/"
	@echo "  format                   ruff format src tests"
	@echo "  format-check             ruff format --check src tests (CI gate)"
	@echo ""
	@echo "Pre-commit:"
	@echo "  precommit-install        Install pre-commit hooks into .git/hooks"
	@echo "  precommit                Run all pre-commit hooks against the worktree"
	@echo ""
	@echo "Database:"
	@echo "  db-upgrade               Run alembic upgrade head"
	@echo "  db-downgrade             Roll back the most recent migration"
	@echo "  db-current               Show current Alembic revision"
	@echo "  init-db                  Create tables via alembic (fallback: create_all)"
	@echo ""
	@echo "ML / MLOps:"
	@echo "  generate-data            Generate synthetic train/test/reference parquet"
	@echo "  train-baseline           Train baseline models locally (no MLflow)"
	@echo "  train-mlflow             Train + log to MLflow + register champion"
	@echo "  mlflow-runs              List recent MLflow runs"
	@echo "  promote-model VERSION=N  Promote registered model version N to Production"
	@echo "  seed-logs                Insert ~100 demo prediction logs"
	@echo "  seed-drift               Insert ~500 drifted prediction logs"
	@echo "  drift-check              Run Evidently drift check + save report"
	@echo "  run-monitoring-flow      Run the Prefect monitoring flow once"
	@echo "  run-retraining-flow      Run the Prefect retraining flow once"
	@echo "  deploy-prefect-flows     Register cron-scheduled Prefect flows"
	@echo ""
	@echo "Smoke + load:"
	@echo "  smoke-health             curl /health"
	@echo "  smoke-predict            curl /v1/predict with sample payload"
	@echo "  smoke-monitoring         curl /v1/monitoring/stats"
	@echo "  smoke-full               run the full Python smoke test"
	@echo "  load-test                Send 100 demo predictions via /v1/predict"
	@echo ""
	@echo "Observability:"
	@echo "  metrics                  curl /metrics on the API"
	@echo "  prometheus-targets       Show Prometheus scrape targets state"
	@echo "  grafana-url              Print Grafana URL + admin/admin login"
	@echo "  monitoring-smoke         Generate traffic + show fraudshield_* metrics"
	@echo ""
	@echo "Admin (require API_KEY):"
	@echo "  trigger-retrain          POST /v1/admin/retrain"
	@echo "  trigger-monitoring       POST /v1/admin/monitoring/run"
	@echo "  trigger-reload           POST /v1/admin/reload-model"
	@echo ""
	@echo "Phase suites:"
	@echo "  phase6-test              Phase 6 unit + integration tests"
	@echo "  phase7-test              Phase 7 metric tests"
	@echo "  phase9-test              Lint + tests + frontend build + smoke (full gate)"
	@echo "  readiness-check          Phase 10 — confirm the repo is publish-ready"
	@echo "  phase10-check            Alias for readiness-check"

# ------------------------------------------------------------------
# Setup + infra
# ------------------------------------------------------------------

setup:
	cd backend && python -m pip install --upgrade pip \
		&& pip install -r requirements.txt -r requirements-dev.txt
	cd frontend && npm install

dev:
	cd backend && uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

docker-up:
	$(COMPOSE) up --build -d

docker-down:
	$(COMPOSE) down

docker-build:
	$(COMPOSE) build

docker-ps:
	$(COMPOSE) ps

docker-restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f

clean:
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/.coverage backend/htmlcov
	rm -rf backend/coverage.xml backend/.prefect-test
	rm -rf frontend/.next frontend/node_modules/.cache
	find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

test: test-backend

test-backend:
	cd backend && pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=65

test-frontend: build-frontend

build-frontend:
	cd frontend && npm run build

# ------------------------------------------------------------------
# Lint + format
# ------------------------------------------------------------------

lint: lint-backend lint-frontend

lint-backend:
	cd backend && ruff check src tests

lint-frontend:
	cd frontend && npm run lint

lint-all: lint format-check

format: format-backend

format-backend:
	cd backend && ruff format src tests

format-check:
	cd backend && ruff format --check src tests

# ------------------------------------------------------------------
# Pre-commit
# ------------------------------------------------------------------

precommit-install:
	pre-commit install

precommit:
	pre-commit run --all-files

# ------------------------------------------------------------------
# Database
# ------------------------------------------------------------------

db-upgrade:
	cd backend && alembic upgrade head

db-downgrade:
	cd backend && alembic downgrade -1

db-current:
	cd backend && alembic current

init-db:
	python backend/scripts/init_db.py

# ------------------------------------------------------------------
# ML / MLOps
# ------------------------------------------------------------------

generate-data:
	cd backend && python scripts/generate_data.py

train-baseline:
	cd backend && python -m src.training.train

train-mlflow:
	cd backend && MLFLOW_TRACKING_URI=$(MLFLOW_TRACKING_URI) python scripts/train_with_mlflow.py

mlflow-runs:
	cd backend && MLFLOW_TRACKING_URI=$(MLFLOW_TRACKING_URI) python scripts/list_mlflow_runs.py

promote-model:
	@if [ -z "$(VERSION)" ]; then echo "usage: make promote-model VERSION=<n>"; exit 1; fi
	cd backend && MLFLOW_TRACKING_URI=$(MLFLOW_TRACKING_URI) python scripts/promote_model.py --version $(VERSION) --stage Production

seed-logs:
	python backend/scripts/seed_prediction_logs.py

seed-drift:
	python backend/scripts/seed_drifted_predictions.py --n 500

drift-check:
	python backend/scripts/run_drift_check.py

# ------------------------------------------------------------------
# Phase 6 — Prefect
# ------------------------------------------------------------------

run-monitoring-flow:
	python backend/scripts/run_monitoring_flow.py

run-retraining-flow:
	python backend/scripts/run_retraining_flow.py --trigger manual

deploy-prefect-flows:
	python backend/scripts/deploy_prefect_flows.py

start-prefect-worker:
	python backend/scripts/start_prefect_worker.py

retraining-runs:
	curl -s http://localhost:$(API_PORT)/v1/retraining/runs | python -m json.tool

trigger-retrain:
	curl -s -X POST http://localhost:$(API_PORT)/v1/admin/retrain \
		-H "X-API-Key: $(API_KEY)" \
		-H "Content-Type: application/json" \
		-d '{"trigger_reason":"manual"}' | python -m json.tool

trigger-monitoring:
	curl -s -X POST http://localhost:$(API_PORT)/v1/admin/monitoring/run \
		-H "X-API-Key: $(API_KEY)" | python -m json.tool

trigger-reload:
	curl -s -X POST http://localhost:$(API_PORT)/v1/admin/reload-model \
		-H "X-API-Key: $(API_KEY)" | python -m json.tool

# ------------------------------------------------------------------
# Phase 4–7 test bundles (kept for incremental gates)
# ------------------------------------------------------------------

api-test:
	cd backend && pytest tests/unit/test_schemas.py tests/unit/test_predictor.py tests/integration/test_predict_endpoint.py tests/integration/test_model_endpoint.py -v --tb=short

logs-api-test:
	cd backend && pytest tests/unit/test_prediction_log_model.py tests/unit/test_prediction_log_repository.py tests/integration/test_prediction_logging.py tests/integration/test_logs_endpoint.py -v --tb=short

drift-api-test:
	cd backend && pytest tests/unit/test_drift_detection.py tests/unit/test_monitoring_data_loader.py tests/unit/test_drift_report_repository.py tests/integration/test_monitoring_endpoints.py -v --tb=short

phase6-test:
	cd backend && pytest tests/unit/test_monitoring_flow.py tests/unit/test_retraining_flow.py tests/unit/test_retraining_repository.py tests/unit/test_admin_auth.py tests/integration/test_admin_retrain_endpoint.py tests/integration/test_retraining_endpoints.py -v --tb=short

phase7-test: metrics-test
metrics-test:
	cd backend && pytest tests/unit/test_metrics.py tests/integration/test_metrics_endpoint.py -v --tb=short

# ------------------------------------------------------------------
# Observability helpers
# ------------------------------------------------------------------

metrics:
	curl -s http://localhost:$(API_PORT)/metrics | head -60

prometheus-targets:
	curl -s http://localhost:9090/api/v1/targets | python -m json.tool

grafana-url:
	@echo "Grafana:    http://localhost:3001"
	@echo "User:       admin"
	@echo "Password:   admin"
	@echo "Dashboards: FraudShield folder"

monitoring-smoke:
	@echo "1. Generating prediction traffic..."
	@for i in 1 2 3 4 5; do \
		curl -s -o /dev/null -X POST http://localhost:$(API_PORT)/v1/predict \
			-H "Content-Type: application/json" \
			-d @backend/scripts/sample_transaction.json || true; \
	done
	@echo "2. fraudshield_* metrics surfaced on /metrics:"
	@curl -s http://localhost:$(API_PORT)/metrics | grep -E "^fraudshield_" | head -30
	@echo ""
	@echo "Open Grafana: http://localhost:3001  (admin/admin)"

# ------------------------------------------------------------------
# Phase 9 — Smoke + load
# ------------------------------------------------------------------

smoke-health:
	curl -fsS http://localhost:$(API_PORT)/health | python -m json.tool

smoke-predict:
	curl -s -X POST http://localhost:$(API_PORT)/v1/predict \
		-H "Content-Type: application/json" \
		-d @backend/scripts/sample_transaction.json | python -m json.tool

smoke-monitoring:
	curl -s http://localhost:$(API_PORT)/v1/monitoring/stats | python -m json.tool

smoke-full:
	python backend/scripts/run_smoke_test.py --base-url $(SMOKE_BASE_URL)

load-test:
	python backend/scripts/send_demo_predictions.py --base-url $(SMOKE_BASE_URL) --n 100

# ------------------------------------------------------------------
# Phase 9 — full gate
# ------------------------------------------------------------------

phase9-test: lint format-check test-backend build-frontend
	@echo ""
	@echo "✓ Phase 9 gate passed: lint + format-check + tests + frontend build"

# ------------------------------------------------------------------
# Phase 10 — pre-publish readiness check
# ------------------------------------------------------------------

readiness-check:
	python backend/scripts/project_readiness_check.py

phase10-check: readiness-check
