# Phase Plan

The full 10-phase implementation roadmap. Each phase has explicit acceptance criteria and ends with a gate before moving on. Do not skip phases.

---

## Phase 0 — Project Scaffolding ✅ *(complete)*

Working monorepo skeleton, all 7 Docker services starting, basic health endpoint.

**Acceptance criteria:**
- `make docker-up` → all 7 containers healthy
- `curl localhost:8001/health` → `{"status": "ok"}` (host 8001 → container 8000)
- MLflow UI loads at `:5000`
- Prefect UI loads at `:4200`
- Grafana login at `:3001`
- Next.js placeholder at `:3000`
- `pytest backend/tests/integration/test_health_endpoint.py` passes
- GitHub CI green

---

## Phase 1 — Data Layer & Feature Engineering ✅ *(complete)*

Synthetic data generator, sklearn feature pipeline, data validators, baseline trainer.

**Key files:** `backend/src/data/generator.py`, `backend/src/features/`, `backend/scripts/generate_data.py`, `backend/src/training/{train,evaluate,builders}.py`.

---

## Phase 2 — Model Training & MLflow Integration ✅ *(complete)*

All baselines (LR / RF / XGBoost) are trained inside MLflow runs with full params + metrics + artifacts logged. The best PR-AUC model is registered as `fraud-detector` and aliased `champion`; `scripts/promote_model.py` flips the `production` alias.

**Acceptance criteria (met):**
- `make train-mlflow` creates the `fraud-detection` experiment and one run per model.
- Each run logs `pr_auc`, `roc_auc`, `precision`, `recall`, `f1_score`, `optimal_threshold`, `training_duration_seconds`, plus model + config artifacts.
- The full sklearn `Pipeline` (preprocessor + classifier) is logged with `mlflow.sklearn.log_model` so Phase 3 can load it without retraining the preprocessor.
- Champion is selected by PR-AUC and registered as `fraud-detector`.
- `make promote-model VERSION=N` aliases the chosen version as `production` and tags older versions `Archived`.
- `backend/reports/mlflow_training_summary.json` is produced.
- Unit tests in `test_experiment_tracking.py` + `test_model_registry.py` run without a live MLflow server.

**Note on MLflow 3.x:** the legacy `Stage` taxonomy was removed; we use the alias `production` plus a `stage` tag on each version to model the same semantics.

---

## Phase 3 — FastAPI Model Serving ✅ *(complete)*

Single + batch prediction endpoints, Prometheus metrics, Pydantic v2 schemas, MLflow loader with dummy fallback.

---

## Phase 4 — PostgreSQL Prediction Logging + Audit Trail ✅ *(complete)*

Every prediction is written to a versioned `prediction_logs` table managed by Alembic. The serving layer becomes the source of truth for the audit trail and the Phase 5 drift baseline.

**Key files:** `backend/src/db/{base,session}.py`, `backend/src/db/models/prediction.py`, `backend/src/db/repositories/prediction_logs.py`, `backend/src/api/routers/{predict,logs,health}.py`, `backend/alembic/versions/phase_4_create_prediction_logs.py`, `backend/scripts/{init_db,seed_prediction_logs}.py`.

**Acceptance criteria (met):**
- `alembic upgrade head` creates the `prediction_logs` table with descending-timestamp and predicted-label indexes; downgrade reverses cleanly.
- `make db-upgrade` runs the migration from the `backend/` directory.
- `POST /v1/predict` and `POST /v1/predict/batch` persist one row per scored transaction (model version, model stage, threshold, latency, raw input features in JSONB).
- `GET /v1/logs` returns paginated, filterable history (`limit`, `offset`, `label`, `min_prob`, `max_prob`, `start_date`, `end_date`); `GET /v1/logs/{id}` returns the detail row including `input_features`; `GET /v1/logs/stats/summary` returns aggregate counts/averages.
- `/ready` reports both `model_loaded` and `db_connected` and returns 503 if either is false.
- Prediction logging is best-effort: a DB failure does not affect the prediction response (enforced by `test_predict_succeeds_even_if_logging_fails`).
- All unit + integration tests for the new layer run on SQLite in-memory (no real Postgres required).

---

## Phase 5 — Evidently Drift Detection ✅ *(complete)*

Evidently 0.7 `DataDriftPreset` comparing the training reference parquet against the most-recent `prediction_logs.input_features` window. Manual trigger only — Prefect automation lands in Phase 6.

**Key files:** `backend/src/monitoring/{__init__,data_loader,drift,reports}.py`, `backend/src/db/models/drift_report.py`, `backend/src/db/repositories/drift_reports.py`, `backend/src/api/routers/monitoring.py`, `backend/alembic/versions/phase_5_create_drift_reports.py`, `backend/scripts/{run_drift_check,seed_drifted_predictions}.py`.

**Acceptance criteria (met):**
- `alembic upgrade head` creates the `drift_reports` table with a unique `report_id`, `generated_at` descending index, and a `drift_detected` index; downgrade reverses cleanly.
- `make seed-logs` + `make seed-drift` populate the `prediction_logs` table with normal + intentionally-shifted feature distributions.
- `make drift-check` runs Evidently against the reference parquet, writes HTML + JSON artifacts under `backend/reports/drift/`, and inserts a `drift_reports` row.
- `POST /v1/monitoring/drift/check` does the same via HTTP, returning the headline metrics + a deep link to the HTML.
- `GET /v1/monitoring/drift-reports` (list, filter by `drift_detected`), `/latest`, `/{report_id}`, `/{report_id}/html`, and `/v1/monitoring/stats` all work.
- Insufficient prediction-log windows return `status="skipped"`, not HTTP 500.
- Evidently is patched at `DriftDetector.run` in tests, so the unit + integration suite (`make drift-api-test`) runs without the real Evidently runtime or a Postgres container.

---

## Phase 6 — Prefect Orchestration & Auto-Retraining ✅ *(complete)*

`monitoring_flow` (every 6h) and `retraining_flow` (weekly). Admin endpoints under `/v1/admin/*` (API-key protected). Retraining-runs audit table + read endpoints under `/v1/retraining/*`. Hot model reload. Champion-vs-challenger comparison gated by `MODEL_PROMOTION_MIN_DELTA` (default 0.01 PR-AUC).

**Key files:** `backend/src/workflows/{monitoring_flow,retraining_flow,deployment,tasks}.py`, `backend/src/api/routers/{admin,retraining}.py`, `backend/src/db/models/retraining_run.py`, `backend/src/db/repositories/retraining_runs.py`, `backend/alembic/versions/phase_6_create_retraining_runs.py`, `backend/scripts/{run_monitoring_flow,run_retraining_flow,deploy_prefect_flows,start_prefect_worker}.py`.

**Acceptance criteria:** `make db-upgrade` creates the `retraining_runs` table; `make run-monitoring-flow` and `make run-retraining-flow` succeed; `make phase6-test` is green; `POST /v1/admin/retrain` with a valid API key returns 200; an invalid key returns 403; the monitoring flow triggers retraining when `drift_detected=True`; the retraining flow only promotes a challenger that improves PR-AUC by `MODEL_PROMOTION_MIN_DELTA` or more.

---

## Phase 7 — Prometheus + Grafana Dashboards ✅ *(complete)*

Custom Prometheus metrics namespace (`fraudshield_*`) covering request volume/latency/error rate, prediction counts + score histogram + batch size, model version + load timestamp, drift score + checks + events, and retraining runs + promotions + PR-AUC of champion vs challenger. Four auto-provisioned Grafana dashboards in the `FraudShield` folder — API Performance, Model Behavior, Drift & Retraining, System Health. Prometheus scrapes `api:8000/metrics` every 15 seconds.

**Key files:** `backend/src/core/metrics.py`, `backend/src/api/middleware/{__init__,metrics}.py`, `infra/prometheus/prometheus.yml`, `infra/grafana/provisioning/{datasources,dashboards}/`.

**Acceptance criteria:** `make metrics` shows the `fraudshield_*` series; `make prometheus-targets` shows `fraudshield-api` UP; Grafana at http://localhost:3001 auto-loads the four dashboards; `make phase7-test` is green.

---

## Phase 8 — Next.js Frontend Dashboard ✅ *(complete)*

Six App Router pages (`/`, `/predict`, `/monitoring`, `/experiments`, `/logs`, `/settings`) consuming the real FastAPI backend through a typed API client. Premium dark-mode shell (sidebar + topbar with live API status), reusable Tailwind UI primitives (Card, Button, Badge, Input, Select, Table, Skeleton), Recharts visualisations (fraud rate, drift score, score distribution, retraining donut), Predict form with one-click sample payloads, admin actions protected by a sessionStorage-only API key.

**Key files:** `frontend/src/app/{layout,page,predict,monitoring,experiments,logs,settings}/*`, `frontend/src/components/*`, `frontend/src/components/charts/*`, `frontend/src/components/ui/*`, `frontend/src/lib/{api,utils,constants,samples}.ts`, `frontend/src/types/index.ts`.

**Acceptance criteria:** `npm run build` + `npm run lint` pass; dashboard loads at http://localhost:3000; Predict form submits to `/v1/predict` and renders the response; Monitoring page lists drift_reports and triggers `/v1/monitoring/drift/check`; Settings page calls `/v1/admin/*` with the stored API key; mobile layout works at 375px width.

---

## Phase 9 — CI/CD, Complete Testing, Polish ✅ *(complete)*

Backend coverage at 76% (gate ≥65%), 220 tests passing in ~75s without live infra. Multi-stage non-root Docker images for backend + frontend with optional corporate-proxy CA bundle, healthchecks on every Compose service, GHA workflows for CI (4 parallel jobs: lint, frontend build, docker build, pre-commit) and CD (safe to merge — only pushes to GHCR when secrets exist), tightened pre-commit (large-files, detect-private-key, end-of-file-fixer), `make smoke-full` / `make load-test` end-to-end probes, centralized `backend/pyproject.toml` for pytest + coverage configuration.

**Key files:** `.github/workflows/{ci,cd}.yml`, `.pre-commit-config.yaml`, `backend/pyproject.toml`, `backend/scripts/{run_smoke_test,send_demo_predictions}.py`, `backend/Dockerfile` (non-root + conditional CA), `frontend/Dockerfile` (multi-stage + healthcheck), `infra/docker-compose.yml` (healthchecks on every service), `Makefile` (full Phase 9 target set).

**Acceptance criteria:** `make docker-build`, `make docker-up`, `make smoke-full`, `make test-backend` (≥65% coverage), `make lint`, `make format-check`, `make precommit`, `make build-frontend`, `make load-test` all pass; no secrets in the repo; `.env.example` is complete.

---

## Phase 10 — Deployment & Documentation

Live public deployment (Vercel + Render), complete docs, screenshots, demo video.

---

See [FRAUDSHIELD_BLUEPRINT.md](../FRAUDSHIELD_BLUEPRINT.md) §8 for the high-level summary.
