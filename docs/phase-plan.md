# Phase Plan

The full 10-phase implementation roadmap. Each phase has explicit acceptance criteria and ends with a gate before moving on. Do not skip phases.

---

## Phase 0 — Project Scaffolding ✅ *(in progress)*

Working monorepo skeleton, all 7 Docker services starting, basic health endpoint.

**Acceptance criteria:**
- `make docker-up` → all 7 containers healthy
- `curl localhost:8000/health` → `{"status": "ok"}`
- MLflow UI loads at `:5000`
- Prefect UI loads at `:4200`
- Grafana login at `:3001`
- Next.js placeholder at `:3000`
- `pytest backend/tests/integration/test_health_endpoint.py` passes
- GitHub CI green

---

## Phase 1 — Data Layer & Feature Engineering

Synthetic data generator, sklearn feature pipeline, data validators.

---

## Phase 2 — Model Training & MLflow Integration

Train 3 models (LR / XGBoost / LightGBM), log to MLflow, register best as Production.

---

## Phase 3 — FastAPI Model Serving

Single + batch prediction endpoints, PostgreSQL prediction logging, Prometheus metrics, Pydantic v2 schemas.

---

## Phase 4 — Evidently Drift Detection

Drift detection function, HTML + DB reports, monitoring API endpoints.

---

## Phase 5 — Prefect Orchestration & Auto-Retraining

`monitoring_flow` (every 6h) and `retrain_flow`. Admin endpoints. Hot model reload.

---

## Phase 6 — Prometheus + Grafana Dashboards

All 4 Grafana dashboards (API perf, model behavior, drift, system health) auto-provisioned.

---

## Phase 7 — Next.js Frontend Dashboard

All 6 pages (Dashboard, Predict, Monitoring, Experiments, Logs, Settings).

---

## Phase 8 — CI/CD, Complete Testing, Polish

Full unit + integration test coverage ≥65%, pre-commit hooks, CD pipeline.

---

## Phase 9 — Deployment & Documentation

Live public deployment (Vercel + Render), complete docs, screenshots, demo video.

---

See [FRAUDSHIELD_BLUEPRINT.md](../FRAUDSHIELD_BLUEPRINT.md) §8 for the high-level summary.
