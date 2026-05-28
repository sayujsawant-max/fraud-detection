# API Reference

> **Status:** Phase 0 endpoints only. Full reference grows phase by phase.

Live OpenAPI/Swagger UI is served at `http://localhost:8000/docs` whenever the API container is running.

## Phase 0 Endpoints

| Method | Path        | Description                                          |
| ------ | ----------- | ---------------------------------------------------- |
| GET    | `/`         | Service metadata (name, version, docs link)          |
| GET    | `/health`   | Liveness probe                                       |
| GET    | `/ready`    | Readiness probe (extended in Phase 3)                |
| GET    | `/metrics`  | Prometheus metrics (scraped every 15s)               |
| GET    | `/docs`     | Swagger UI                                           |
| GET    | `/redoc`    | ReDoc UI                                             |
| GET    | `/openapi.json` | OpenAPI schema                                   |

## Coming in Later Phases

- `POST /v1/predict` — single prediction (Phase 3)
- `POST /v1/predict/batch` — batch prediction (Phase 3)
- `GET /v1/model/info` — current production model metadata (Phase 3)
- `GET /v1/monitoring/drift-reports` — list drift reports (Phase 4)
- `GET /v1/experiments` — MLflow runs (Phase 5)
- `POST /v1/admin/retrain` — trigger retraining (Phase 5, API-key protected)
- `POST /v1/admin/reload-model` — hot-reload model (Phase 5, API-key protected)
- `GET /v1/logs` — prediction history (Phase 5)
