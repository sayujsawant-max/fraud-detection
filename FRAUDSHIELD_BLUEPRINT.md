# FraudShield MLOps — Complete Senior Engineer Blueprint

> **Version:** 1.0 | **Status:** Pre-implementation reference | **Audience:** You + future interviewers

---

## 1. Final Project Name

**FraudShield MLOps**

- GitHub repo: `fraudshield-mlops`
- Docker namespace: `fraudshield`
- All service prefixes: `fraudshield-*`

---

## 2. One-Line Description

> A production-grade, end-to-end MLOps platform for real-time fraud detection — featuring model serving, automated drift monitoring, scheduled retraining, experiment tracking, and live observability dashboards — fully containerized with Docker Compose and publicly deployable.

---

## 3. Interview Pitch (30-Second Version)

> "FraudShield is a full MLOps system I built from scratch — not a notebook, a platform. It serves an XGBoost fraud detection model through a versioned FastAPI, tracks every experiment in MLflow, automatically detects data drift using Evidently AI, and triggers retraining pipelines through Prefect when drift exceeds a threshold. Everything is instrumented with Prometheus and visualized in Grafana. The frontend is a Next.js dashboard where you can submit transactions, see fraud probabilities in real time, and inspect drift reports. It runs locally with one Docker Compose command and is deployed publicly. I designed it to be modular so Kubernetes can be layered in as a future upgrade."

---

## 4. Why This Project Is Impressive for Interviews

**Most candidates show:** A Jupyter notebook with model.fit(), maybe a Streamlit app.

**You show:** A system. Here is exactly what it demonstrates for each role:

| Role | What This Project Proves |
|---|---|
| **ML Engineer** | You understand the full lifecycle beyond training: versioning, serving, monitoring |
| **MLOps Engineer** | You can wire together the real toolchain: MLflow + Evidently + Prefect + Prometheus + Grafana |
| **Data Scientist** | You understand model degradation, drift, retraining strategy, and evaluation metrics |
| **AI Engineer** | You can deploy models as production APIs with versioning and rollback |
| **Backend Engineer** | You built a multi-service FastAPI system with proper routing, middleware, logging, and a database |
| **Frontend Engineer** | You built a typed Next.js dashboard that consumes your own ML API |
| **DevOps / Platform** | You Dockerized a 7-service system, wrote CI/CD pipelines, and planned cloud deployment |

The rarity: this intersection of skills is exceptional at the intern/new-grad level and competitive at the junior engineer level.

---

## 5. Full Architecture Explanation

FraudShield is composed of six logical layers, each independently scalable:

**Data Layer:** A synthetic fraud transaction generator produces realistic datasets with configurable fraud rate (~4.5%), feature distributions, and temporal patterns. The reference dataset snapshot is stored separately and used as the drift baseline.

**Training Layer:** A Prefect-orchestrated training pipeline reads data, runs feature engineering through a Scikit-learn Pipeline object, trains three model variants (Logistic Regression baseline, XGBoost champion, LightGBM challenger), evaluates all three, logs everything to MLflow, and registers the best model in the MLflow Model Registry tagged as "Production."

**Serving Layer:** FastAPI loads the Production model from the registry at startup via the MLflow client. Every prediction request is validated by Pydantic v2, runs through the same preprocessing pipeline (bundled inside the MLflow artifact), and returns fraud probability + label + model version. Every prediction is asynchronously logged to PostgreSQL. Prometheus metrics are emitted on every request.

**Monitoring Layer:** Prometheus scrapes the `/metrics` endpoint every 15 seconds. Grafana reads Prometheus and renders four dashboards covering API performance, model behavior, drift signals, and system health. Evidently AI runs on a schedule, comparing recent prediction inputs against the reference distribution and generating HTML + JSON drift reports.

**Orchestration Layer:** Prefect manages two flows — a monitoring flow that runs every 6 hours to check drift, and a retraining flow that runs on trigger or weekly schedule. If drift exceeds threshold, the monitoring flow calls the retraining flow. The retraining flow trains a challenger model, compares it to the current champion, and promotes it if it wins.

**Frontend Layer:** A Next.js dashboard provides a human interface for the entire system — a prediction form, KPI cards, drift report viewer, MLflow experiment table, prediction log browser, and admin actions (manual retrain trigger, model reload).

---

## 6. Tech Stack (Summary)

| Tool | Layer | Why |
|---|---|---|
| Python 3.11 | All | ML ecosystem standard |
| FastAPI + Pydantic v2 + Uvicorn | Serving | Async, OpenAPI docs, fast |
| XGBoost / LightGBM / scikit-learn | ML | Tabular fraud detection |
| MLflow | Tracking + Registry | Free, self-hostable |
| Evidently AI | Drift | Best OSS ML monitoring |
| Prefect 3 | Orchestration | Python-native DAGs |
| Prometheus + Grafana | Observability | Standard metrics stack |
| PostgreSQL 16 + SQLAlchemy 2 + Alembic | Storage | Production RDBMS |
| Next.js 14 + Tailwind | Frontend | SSR, file-based routing |
| Docker Compose v2 | Infra | One-command local stack |
| GitHub Actions | CI/CD | Native, free for public |
| Loguru, slowapi, Ruff, pytest, httpx | Dev quality | Best-in-class tools |

---

## 7. Folder Structure (Monorepo)

```
fraudshield-mlops/
├── backend/        FastAPI service, ML training, monitoring, Prefect flows
├── frontend/       Next.js 14 dashboard
├── infra/          docker-compose + Prometheus + Grafana provisioning + MLflow Dockerfile
├── docs/           Architecture, deployment, interview, API reference
├── .github/        CI/CD workflows
└── (root configs)  Makefile, .env.example, .gitignore, ruff, pre-commit
```

See [docs/phase-plan.md](docs/phase-plan.md) for the detailed 10-phase implementation roadmap.

---

## 8. Implementation Phases (Summary)

- **Phase 0** — Project scaffolding (this phase). Working monorepo skeleton, all 7 Docker services starting, basic health endpoint.
- **Phase 1** — Data layer & feature engineering. Synthetic data generator + sklearn Pipeline.
- **Phase 2** — Model training & MLflow integration.
- **Phase 3** — FastAPI model serving with PostgreSQL logging.
- **Phase 4** — Evidently drift detection.
- **Phase 5** — Prefect orchestration & auto-retraining.
- **Phase 6** — Prometheus + Grafana dashboards.
- **Phase 7** — Next.js frontend dashboard.
- **Phase 8** — CI/CD, complete testing, polish.
- **Phase 9** — Deployment & documentation.

Each phase has explicit acceptance criteria and commands. Do not skip phases.

---

## 9. Key Design Decisions

- **PR-AUC over AUC-ROC** for model selection on imbalanced fraud data
- **Full sklearn Pipeline bundled into the MLflow artifact** to eliminate training–serving skew
- **Optimal threshold stored as artifact**, not hardcoded to 0.5
- **Drift threshold = 0.30** (share_of_drifted_columns), configurable via env
- **Async prediction logging** to PostgreSQL — never blocks the prediction path
- **Hot model reload** via `POST /v1/admin/reload-model` — no container restart needed
- **API key on `/v1/admin/*`** endpoints; rate limit on prediction endpoints

---

## 10. Interview Talking Points

- "Walk me through your project" — covers the six layers and how they interact
- "Why XGBoost for fraud detection?" — PR-AUC fit, scale_pos_weight, calibrated probs
- "How does your drift detection work?" — Evidently DataDrift, share_of_drifted_columns threshold, triggers retrain flow
- "How would you scale this?" — Kubernetes swap-in, stateless FastAPI horizontal scaling, async queue for prediction logging, S3 for MLflow artifacts
- "What would you do differently?" — Feature store, A/B shadow testing, ground-truth chargeback feedback loop, SHAP per-prediction explanations

---

*Blueprint version 1.0 — FraudShield MLOps — Source of truth for implementation.*
*Start with Phase 0. Do not skip phases. Each phase's acceptance criteria is a real gate.*
