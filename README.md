# FraudShield MLOps

> A production-grade, end-to-end MLOps platform for real-time fraud detection — featuring model serving, automated drift monitoring, scheduled retraining, experiment tracking, and live observability dashboards.

![Status](https://img.shields.io/badge/status-phase--0--scaffold-blue)
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

# 5. Verify the API is alive
curl http://localhost:8000/health
```

> **Behind a corporate proxy (Zscaler, Cisco Umbrella, etc.)?** Docker build containers can't see your Windows certificate store, so pip and npm fail with `CERTIFICATE_VERIFY_FAILED` / `UNABLE_TO_VERIFY_LEAF_SIGNATURE`. The script in step 3 exports your host's trusted roots into `backend/certs/ca-bundle.pem` and `frontend/certs/ca-bundle.pem` — both Dockerfiles install that bundle before downloading any packages. The bundle is gitignored.

---

## Services

| Service     | URL                       | Purpose                       |
| ----------- | ------------------------- | ----------------------------- |
| FastAPI     | http://localhost:8000     | Prediction API + `/docs`      |
| MLflow      | http://localhost:5000     | Experiments + Model Registry  |
| Prefect     | http://localhost:4200     | Workflow orchestration UI     |
| Prometheus  | http://localhost:9090     | Metrics scraping              |
| Grafana     | http://localhost:3001     | Observability dashboards      |
| PostgreSQL  | localhost:5432            | Prediction + drift storage    |
| Frontend    | http://localhost:3000     | Next.js dashboard             |

---

## Development Commands

```bash
make setup         # Install local Python and Node dependencies
make dev           # Run backend locally (uvicorn reload)
make test          # Run backend test suite
make lint          # Run ruff linting
make format        # Run ruff formatter
make docker-up     # Start all 7 services via Docker Compose
make docker-down   # Stop all services
make docker-build  # Rebuild all images
make logs          # Tail Docker Compose logs
make clean         # Remove caches and build artifacts
```

---

## Project Status — Phase 0 (Scaffolding)

Phase 0 establishes the monorepo skeleton, Docker infrastructure, FastAPI health endpoints, Next.js placeholder UI, and CI. No ML logic is implemented yet.

### Working in Phase 0
- All 7 Docker Compose services boot cleanly
- FastAPI `/`, `/health`, `/ready`, `/metrics` endpoints
- Next.js placeholder landing page
- GitHub Actions CI: ruff + pytest on the health endpoint

### Coming in later phases
- **Phase 1** — Synthetic data generator + feature engineering pipeline
- **Phase 2** — MLflow experiment tracking + model registry
- **Phase 3** — Real model serving with PostgreSQL prediction logging
- **Phase 4** — Evidently AI drift detection
- **Phase 5** — Prefect monitoring + auto-retraining flows
- **Phase 6** — Prometheus + Grafana dashboards
- **Phase 7** — Full Next.js dashboard
- **Phase 8** — Full test suite + CD pipeline
- **Phase 9** — Public deployment (Vercel + Render)

See [docs/phase-plan.md](docs/phase-plan.md) for the full implementation roadmap.

---

## License

MIT — see [LICENSE](LICENSE).
