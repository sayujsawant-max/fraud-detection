# FraudShield MLOps

> A production-grade, end-to-end MLOps platform for real-time fraud detection — featuring model serving, automated drift monitoring, scheduled retraining, experiment tracking, and live observability dashboards.

![Status](https://img.shields.io/badge/status-phase--9--ci%2Fcd--hardening-blue)
[![CI](https://github.com/sayujsawant-max/fraud-detection/actions/workflows/ci.yml/badge.svg)](https://github.com/sayujsawant-max/fraud-detection/actions/workflows/ci.yml)
[![CD](https://github.com/sayujsawant-max/fraud-detection/actions/workflows/cd.yml/badge.svg)](https://github.com/sayujsawant-max/fraud-detection/actions/workflows/cd.yml)
![Coverage](https://img.shields.io/badge/coverage-76%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688)
![Next.js](https://img.shields.io/badge/Next.js-14-black)
![Docker](https://img.shields.io/badge/docker-compose%20v2-2496ED)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Overview

FraudShield is a full MLOps system — not a notebook. It serves an XGBoost fraud detection model through a versioned FastAPI, tracks every experiment in MLflow, automatically detects data drift using Evidently AI, and triggers retraining pipelines through Prefect when drift exceeds a threshold. Everything is instrumented with Prometheus and visualized in Grafana, fronted by a Next.js dashboard, and runs locally with one Docker Compose command.

> See [FRAUDSHIELD_BLUEPRINT.md](FRAUDSHIELD_BLUEPRINT.md) for the complete senior-engineer design document.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         FRAUDSHIELD MLOPS                            │
│                                                                      │
│   DATA  →  TRAINING  →  MLFLOW REGISTRY  →  FASTAPI  →  POSTGRES     │
│                                ↑               │                     │
│                                │               ↓                     │
│                          RETRAIN FLOW    PROMETHEUS → GRAFANA        │
│                                ↑                                     │
│                                │                                     │
│                         EVIDENTLY DRIFT                              │
│                                ↑                                     │
│                         PREFECT MONITORING                           │
│                                                                      │
│                            NEXT.JS UI                                │
└──────────────────────────────────────────────────────────────────────┘
```

A full ASCII architecture diagram and per-layer explanation lives in [docs/architecture.md](docs/architecture.md).

---

## Tech Stack

| Layer            | Tool                                                |
| ---------------- | --------------------------------------------------- |
| Serving          | FastAPI, Pydantic v2, Uvicorn                       |
| ML               | XGBoost, LightGBM, scikit-learn                     |
| Tracking         | MLflow (experiments + model registry)               |
| Drift            | Evidently AI                                        |
| Orchestration    | Prefect 3                                           |
| Observability    | Prometheus, Grafana                                 |
| Storage          | PostgreSQL 16, SQLAlchemy 2, Alembic                |
| Frontend         | Next.js 14 (App Router), Tailwind CSS, TypeScript   |
| Infrastructure   | Docker Compose v2                                   |
| CI/CD            | GitHub Actions                                      |

---

## Quick Start

```bash
# 1. Clone and enter the repo
git clone https://github.com/<you>/fraudshield-mlops.git
cd fraudshield-mlops

# 2. Configure environment
cp .env.example .env

# 3. (Only behind a TLS-intercepting proxy) Export host CAs into the build contexts
pwsh -File scripts/export-ca-bundle.ps1   # Windows; one-time per machine

# 4. Start the full stack
make docker-up

# 5. Verify the API is alive (Docker maps host 8001 → container 8000)
curl http://localhost:8001/health
```

> **Behind a corporate proxy (Zscaler, Cisco Umbrella, etc.)?** Docker build containers can't see your Windows certificate store, so pip and npm fail with `CERTIFICATE_VERIFY_FAILED` / `UNABLE_TO_VERIFY_LEAF_SIGNATURE`. The script in step 3 exports your host's trusted roots into `backend/certs/ca-bundle.pem` and `frontend/certs/ca-bundle.pem` — both Dockerfiles install that bundle before downloading any packages. The bundle is gitignored.

---

## Services

| Service     | URL                       | Purpose                       |
| ----------- | ------------------------- | ----------------------------- |
| FastAPI     | http://localhost:8001     | Prediction API + `/docs` (host 8001 → container 8000) |
| MLflow      | http://localhost:5000     | Experiments + Model Registry  |
| Prefect     | http://localhost:4200     | Workflow orchestration UI     |
| Prometheus  | http://localhost:9090     | Metrics scraping              |
| Grafana     | http://localhost:3001     | Observability dashboards      |
| PostgreSQL  | localhost:5432            | Prediction + drift storage    |
| Frontend    | http://localhost:3000     | Next.js dashboard             |

---

## Development Commands

```bash
make setup           # Install local Python and Node dependencies
make dev             # Run backend locally (uvicorn reload)
make test            # Run backend test suite
make lint            # Run ruff linting
make format          # Run ruff formatter
make generate-data   # Generate synthetic train/test/reference parquet files
make train-baseline  # Train baselines locally (no MLflow)
make train-mlflow    # Train baselines, log to MLflow, register champion
make mlflow-runs     # List recent runs from the fraud-detection experiment
make promote-model VERSION=N   # Alias version N as production
make run-monitoring-flow       # Run Prefect monitoring flow once (Phase 6)
make run-retraining-flow       # Run Prefect retraining flow once (Phase 6)
make deploy-prefect-flows      # Register cron-scheduled flows (Phase 6)
make trigger-retrain API_KEY=change-me      # Curl POST /v1/admin/retrain
make trigger-monitoring API_KEY=change-me   # Curl POST /v1/admin/monitoring/run
make trigger-reload API_KEY=change-me       # Curl POST /v1/admin/reload-model
make retraining-runs           # Curl GET  /v1/retraining/runs
make phase6-test               # Run Phase 6 unit + integration tests
make metrics                   # Curl GET /metrics on the API (Phase 7)
make prometheus-targets        # Show Prometheus scrape targets state
make grafana-url               # Print Grafana URL + admin/admin login
make monitoring-smoke          # Generate traffic + show fraudshield_* metrics
make phase7-test               # Run Phase 7 metric tests
make docker-up       # Start all 7 services via Docker Compose
make docker-down     # Stop all services
make docker-build    # Rebuild all images
make logs            # Tail Docker Compose logs
make clean           # Remove caches and build artifacts
```

### Train + register a champion model

```bash
# 1. Bring the stack up (MLflow + Postgres + ...)
make docker-up

# 2. Generate the synthetic dataset
make generate-data

# 3. Train all baselines, log to MLflow, register the PR-AUC winner
make train-mlflow

# 4. Open the MLflow UI
#    http://localhost:5000

# 5. List the runs from the terminal
make mlflow-runs

# 6. Promote a model version to Production (alias = "production")
make promote-model VERSION=1
```

> When running locally (not inside Docker), the Make targets set
> `MLFLOW_TRACKING_URI=http://localhost:5000`. Override with
> `make train-mlflow MLFLOW_TRACKING_URI=http://mlflow.example:5000`.

---

## Project Status — Phase 9 (CI/CD + Quality Hardening)

Phases 0–9 are complete. The full Docker Compose stack starts cleanly with healthchecks on every service, backend tests run at **220 passed / 76% coverage** in under 90 seconds, **`make smoke-full`** exercises every API endpoint end-to-end, and **GitHub Actions CI** runs ruff lint + ruff format check + pytest + Next.js lint + Next.js build + Docker buildx for both images + pre-commit hooks in four parallel jobs. The CD workflow is wired up safely — it builds images on every push to `main`, but only pushes to GHCR and fires Render/Vercel deploy hooks when the corresponding secrets are present. **No secrets, parquet datasets, or local artifacts ship with the repo**; `.gitignore` and the per-image `.dockerignore` files keep the surface clean.

### Working today
- All 7 Docker Compose services boot cleanly.
- `make generate-data` → 120k synthetic transactions split 80/20 with a 5k reference dataset.
- `make train-mlflow` → one MLflow run per model in experiment `fraud-detection`, champion registered as `fraud-detector`, aliased `champion`, summary at `backend/reports/mlflow_training_summary.json`.
- `make promote-model VERSION=N` flips the `production` alias and tags older versions `Archived`.
- `make dev` → FastAPI loads the Production model from MLflow (or a dummy fallback for dev) and exposes `/v1/predict`, `/v1/predict/batch`, `/v1/model/info`.
- Full unit + integration test suite (`make api-test`) — runs without Docker, MLflow, or PostgreSQL by injecting a `DummyFraudModel`.

### Phase 3 quick-start (the API — local `make dev` flow, port 8000)
> When running via Docker the API is on **port 8001** instead (see the Phase 4–9 quick-starts below). `make dev` runs uvicorn directly on the host, where it listens on 8000.
```bash
# 1. Local dev with the dummy model (no MLflow needed)
ALLOW_DUMMY_MODEL=true make dev

# 2. Hit it (host port 8000 because make dev runs uvicorn directly)
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/v1/model/info

# 3. Single prediction (sample payload checked into the repo)
make smoke-predict
# or directly:
curl -X POST http://localhost:8000/v1/predict \
     -H "Content-Type: application/json" \
     -d @backend/scripts/sample_transaction.json

# 4. Batch prediction
curl -X POST http://localhost:8000/v1/predict/batch \
     -H "Content-Type: application/json" \
     -d '{"transactions":[<TransactionRequest>, <TransactionRequest>]}'
```

### Real MLflow model vs dummy model
- **Dummy** (`ALLOW_DUMMY_MODEL=true`, default in `.env.example`) — boots the API even when MLflow is missing. Returns a deterministic probability derived from a handful of risk features (`amount_to_avg_ratio`, `is_foreign_transaction`, `ip_risk_score`, …). Identifies itself as `dummy-fraud-model@dev`. Useful for local dev, CI, and smoke tests.
- **Real** (`ALLOW_DUMMY_MODEL=false`) — the loader requires a registered model. It tries `models:/fraud-detector/Production` first, then `models:/fraud-detector@production`, then `models:/fraud-detector@champion`. If none resolve, `/ready` returns 503 and `/v1/predict` returns 503.

### Phase 4 quick-start (audit trail)
```bash
# 1. Start the stack (brings up Postgres + MLflow + API)
make docker-up

# 2. Apply the Alembic migration that creates prediction_logs
make db-upgrade

# 3. Send a prediction — the row is logged automatically
make smoke-predict

# 4. View the audit trail (Docker stack — host port 8001)
curl http://localhost:8001/v1/logs | python -m json.tool

# 5. Aggregate summary stats (used by the dashboard later)
curl http://localhost:8001/v1/logs/stats/summary | python -m json.tool

# 6. (Optional) Backfill demo records
make seed-logs

# 7. Run the Phase 4 test bundle (no Postgres required — SQLite in-memory)
make logs-api-test
```

### Phase 5 quick-start (drift detection)
```bash
# 1. Stack up + migrations
make docker-up
make db-upgrade

# 2. Seed prediction logs — normal baseline + drifted window
make seed-logs        # 100 normal rows
make seed-drift       # 500 rows with shifted feature distributions

# 3. Run a drift check (CLI)
make drift-check
# → writes backend/reports/drift/drift_<ts>.html + .json
# → inserts one drift_reports row

# 4. Trigger a drift check via the API
curl -X POST http://localhost:8001/v1/monitoring/drift/check \
     -H "Content-Type: application/json" \
     -d '{"limit": 1000, "min_samples": 200, "save_report": true}'

# 5. View the latest drift report metadata
curl http://localhost:8001/v1/monitoring/drift-reports/latest | python -m json.tool

# 6. Open the rendered HTML report in a browser
#    http://localhost:8001/v1/monitoring/drift-reports/<report_id>/html

# 7. Aggregate monitoring stats (dashboard surface)
curl http://localhost:8001/v1/monitoring/stats | python -m json.tool

# 8. Run the Phase 5 test bundle (no Postgres / Evidently needed)
make drift-api-test
```

### Phase 6 quick-start (Prefect orchestration)
```bash
# 1. Stack up + migrations (creates retraining_runs table)
make docker-up
make db-upgrade

# 2. Run the monitoring flow once (no Prefect server needed)
make run-monitoring-flow

# 3. Run the retraining flow once
make run-retraining-flow

# 4. Register both flows on cron schedules (blocks; Ctrl+C to stop)
#    Monitoring runs every 6h, retraining runs weekly (Sun 02:00 UTC).
#    Watch the Prefect UI at http://localhost:4200.
make deploy-prefect-flows

# 5. Trigger retraining via the API
make trigger-retrain API_KEY=change-me

# 6. Manually run monitoring via the API
make trigger-monitoring API_KEY=change-me

# 7. Hot-reload the production model after a promotion
make trigger-reload API_KEY=change-me

# 8. List the retraining runs
make retraining-runs

# 9. Inspect aggregate retraining stats
curl http://localhost:8001/v1/retraining/stats | python -m json.tool

# 10. Run the Phase 6 test bundle (no Prefect server / MLflow / Postgres needed)
make phase6-test
```

The Prefect UI ships with the stack at http://localhost:4200 — open it
after `make deploy-prefect-flows` to see the two deployments
(`fraud-monitoring-every-6h`, `fraud-retraining-weekly`) and trigger
ad-hoc runs from there too.

### Phase 7 quick-start (Prometheus + Grafana)
```bash
# 1. Stack up — Prometheus and Grafana are already in docker-compose
make docker-up

# 2. Generate prediction traffic so the metrics have data
make smoke-predict
make seed-logs        # optional: 100 demo prediction logs

# 3. View the raw Prometheus metrics
make metrics
# or: curl http://localhost:8001/metrics

# 4. Open Prometheus and check scrape targets
#    http://localhost:9090
#    Status → Targets → fraudshield-api should be "UP"
make prometheus-targets

# 5. Open Grafana
#    http://localhost:3001  (admin / admin)
make grafana-url

# 6. Dashboards land under the "FraudShield" folder:
#    - FraudShield — API Performance       (req rate, p50/p95/p99, error rate)
#    - FraudShield — Model Behavior        (predictions, fraud rate, score dist)
#    - FraudShield — Drift & Retraining    (drift score, retrain runs, PR-AUC)
#    - FraudShield — System Health         (API up, scrape duration, 5xx rate)

# 7. Generate traffic + show the live metrics in one go
make monitoring-smoke

# 8. Phase 7 test bundle (no Prometheus / Grafana needed)
make phase7-test
```

### Phase 8 quick-start (Next.js dashboard)
```bash
# 1. Stack up (brings up the backend dependencies)
make docker-up

# 2. Open the dashboard (already built + served by the frontend container)
#    http://localhost:3000

# Pages (sidebar):
#   /              Overview — KPIs, model info, recent predictions, charts
#   /predict       Transaction Predictor — full form + result card
#   /monitoring    Drift reports + manual drift check trigger
#   /experiments   MLflow link + retraining-runs audit table
#   /logs          Paginated prediction logs + detail drawer
#   /settings      Admin API key + retrain/reload/monitoring actions

# Local-dev (without Docker) — runs against the API at NEXT_PUBLIC_API_URL:
cd frontend
NODE_OPTIONS=--use-system-ca npm install
NODE_OPTIONS=--use-system-ca npm run dev
#   http://localhost:3000 (Next.js dev server)

# Build / lint:
npm run build          # production build
npm run lint           # ESLint (next/core-web-vitals)
```

### Phase 9 quick-start (CI/CD + quality gates)
```bash
# 1. Install dev tooling locally (Python + Node + pre-commit)
make setup
make precommit-install         # one-time: installs git hooks

# 2. Run the full quality gate in one shot
make phase9-test
#   -> ruff lint + ruff format-check + pytest --cov-fail-under=65 + npm run build

# 3. Or run gates individually:
make lint                      # ruff check + next lint
make format-check              # ruff format --check (CI-style)
make test-backend              # pytest with 65% coverage gate (current: 76%)
make build-frontend            # next build
make precommit                 # run every pre-commit hook against the worktree

# 4. End-to-end probes (need the stack running)
make docker-up                 # bring up the 7-service stack
make smoke-full                # exercise every API endpoint
make load-test                 # send 100 demo predictions

# 5. CI / CD
#   .github/workflows/ci.yml  — runs on push + PR (no secrets needed)
#   .github/workflows/cd.yml  — builds images on push to main; pushes to
#                               GHCR only when secrets.GHCR_TOKEN is set
```

### Coming in later phases
- **Phase 10** — Public deployment (Vercel + Render), screenshots, demo video

See [docs/phase-plan.md](docs/phase-plan.md) for the full implementation roadmap.

---

## License

MIT — see [LICENSE](LICENSE).
