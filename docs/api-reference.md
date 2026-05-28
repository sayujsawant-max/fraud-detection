# API Reference

> **Status:** Phase 5 — drift detection live. Admin / retrain endpoints follow in later phases.

Live OpenAPI/Swagger UI is served at `http://localhost:8001/docs` when running via Docker Compose (host 8001 → container 8000), or `http://localhost:8000/docs` when running locally with `make dev`.

## Endpoint Summary

| Method | Path                  | Description                                          |
| ------ | --------------------- | ---------------------------------------------------- |
| GET    | `/`                   | Service metadata (name, version, docs link)          |
| GET    | `/health`             | Liveness probe                                       |
| GET    | `/ready`              | Readiness probe — 503 if no model loaded             |
| GET    | `/metrics`            | Prometheus metrics (scraped every 15s)               |
| GET    | `/docs`               | Swagger UI                                           |
| GET    | `/redoc`              | ReDoc UI                                             |
| GET    | `/openapi.json`       | OpenAPI schema                                       |
| POST   | `/v1/predict`         | Single-transaction fraud prediction                  |
| POST   | `/v1/predict/batch`   | Batch fraud prediction (up to `MAX_BATCH_SIZE`)      |
| GET    | `/v1/model/info`      | Currently-loaded model metadata                      |
| GET    | `/v1/logs`            | Paginated, filterable prediction history (Phase 4)   |
| GET    | `/v1/logs/{log_id}`   | One prediction log with full `input_features`        |
| GET    | `/v1/logs/stats/summary` | Aggregate counts + averages over all logs         |
| POST   | `/v1/monitoring/drift/check`                  | Run an Evidently drift check on the recent prediction window |
| GET    | `/v1/monitoring/drift-reports`                | Paginated list of drift reports (newest first)  |
| GET    | `/v1/monitoring/drift-reports/latest`         | Newest drift report                              |
| GET    | `/v1/monitoring/drift-reports/{report_id}`    | One drift report with full metadata + JSON       |
| GET    | `/v1/monitoring/drift-reports/{report_id}/html` | Rendered Evidently HTML artifact               |
| GET    | `/v1/monitoring/stats`                        | Aggregate drift counts + averages                |
| POST   | `/v1/admin/retrain`                           | **API key** — Trigger retraining flow            |
| POST   | `/v1/admin/reload-model`                      | **API key** — Hot-reload the production model    |
| POST   | `/v1/admin/monitoring/run`                    | **API key** — Manually trigger monitoring flow   |
| GET    | `/v1/retraining/runs`                         | Paginated retraining runs (newest first)         |
| GET    | `/v1/retraining/runs/latest`                  | Newest retraining run                            |
| GET    | `/v1/retraining/runs/{run_id}`                | One retraining run by UUID                       |
| GET    | `/v1/retraining/stats`                        | Aggregate retraining counts                      |
| GET    | `/metrics`                                    | Prometheus exposition format (Phase 7)           |

## Phase 3 Endpoint Details

### GET /

```json
{ "name": "FraudShield API", "version": "0.1.0", "docs": "/docs" }
```

### GET /health

```json
{ "status": "ok", "version": "0.1.0" }
```

### GET /ready

Phase 4 adds a database probe — `/ready` is 200 only when **both** `model_loaded` and `db_connected` are true.

`200`:
```json
{ "status": "ready", "model_loaded": true, "db_connected": true }
```
`503`:
```json
{ "status": "not_ready", "model_loaded": false, "db_connected": true }
```

### POST /v1/predict

Request body (`TransactionRequest`) — every field is required except `transaction_id`:

```json
{
  "transaction_id": "tx-sample-001",
  "transaction_amount": 142.50,
  "transaction_hour": 14,
  "transaction_day_of_week": 2,
  "is_weekend": 0,
  "merchant_category": "groceries",
  "transaction_type": "purchase",
  "card_type": "visa",
  "transaction_count_24h": 3,
  "transaction_count_7d": 12,
  "avg_transaction_amount_30d": 110.0,
  "amount_to_avg_ratio": 1.30,
  "unique_merchants_7d": 5,
  "is_first_transaction_merchant": 0,
  "distance_from_home_km": 4.2,
  "is_foreign_transaction": 0,
  "is_high_risk_country": 0,
  "device_type": "mobile",
  "browser_type": "chrome",
  "ip_risk_score": 0.12,
  "account_age_days": 540,
  "user_age": 34,
  "credit_limit": 8000.0,
  "credit_utilization": 0.34,
  "previous_fraud_flag": 0,
  "log_amount": 4.96,
  "is_high_velocity": 0,
  "is_new_account": 0,
  "is_late_night": 0,
  "amount_z_score": 0.22
}
```

Response (`PredictionResponse`):
```json
{
  "transaction_id": "tx-sample-001",
  "fraud_probability": 0.27,
  "predicted_label": 0,
  "is_fraud": false,
  "model_name": "fraud-detector",
  "model_version": "3",
  "model_stage": "Production",
  "threshold_used": 0.42,
  "latency_ms": 11.8,
  "timestamp": "2026-05-28T18:33:21.456000+00:00"
}
```

#### Categorical vocabulary

The Pydantic `Literal` types are generated from `src/features/constants.py`, the same module the sklearn pipeline uses at training time:

| Field               | Allowed values                                                                                                  |
| ------------------- | --------------------------------------------------------------------------------------------------------------- |
| `merchant_category` | groceries, restaurants, gas_station, online_retail, electronics, travel, entertainment, healthcare, utilities, gambling, crypto_exchange, luxury_goods |
| `transaction_type`  | purchase, withdrawal, transfer, refund, subscription                                                            |
| `card_type`         | visa, mastercard, amex, discover                                                                                |
| `device_type`       | mobile, desktop, tablet, pos_terminal                                                                           |
| `browser_type`      | chrome, safari, firefox, edge, other, native_app                                                                |

### POST /v1/predict/batch

```json
{ "transactions": [<TransactionRequest>, <TransactionRequest>] }
```
Returns `422` if the list is empty or larger than `MAX_BATCH_SIZE` (default 100).

Response (`BatchPredictionResponse`):
```json
{
  "predictions": [<PredictionResponse>, <PredictionResponse>],
  "batch_size": 2,
  "batch_latency_ms": 23.7,
  "timestamp": "2026-05-28T18:33:21.456000+00:00"
}
```

### GET /v1/model/info

```json
{
  "model_name": "fraud-detector",
  "model_version": "3",
  "model_stage": "Production",
  "model_loaded": true,
  "optimal_threshold": 0.42,
  "feature_count": 29,
  "loaded_at": "2026-05-28T18:30:10.000000+00:00"
}
```

## Error Codes

| Status | Meaning                                                                                       |
| -----: | --------------------------------------------------------------------------------------------- |
| 200    | Success                                                                                       |
| 422    | Pydantic validation failure (range, categorical, missing field, batch over `MAX_BATCH_SIZE`)  |
| 500    | Prediction error or invalid model output. Stack trace logged server-side; safe message only.  |
| 503    | Model is not loaded (`ALLOW_DUMMY_MODEL=false` and the MLflow registry call failed).          |

## Phase 4 Endpoint Details — Prediction Log Audit Trail

Every successful `POST /v1/predict` (and `POST /v1/predict/batch`) is asynchronously persisted to the `prediction_logs` table in PostgreSQL. The write happens *after* the predictor returns and is best-effort: if Postgres is unreachable the API still returns the prediction, the failure is logged via Loguru, and operators can chase it in observability. This is the design rationale in [docs/interview-guide.md](interview-guide.md#why-prediction-should-not-fail-if-audit-logging-fails).

### GET /v1/logs

Query parameters:

| Param        | Type     | Default | Notes                                      |
| ------------ | -------- | ------- | ------------------------------------------ |
| `limit`      | int      | 50      | 1–500                                      |
| `offset`     | int      | 0       | ≥0                                         |
| `label`      | int      | —       | 0 or 1                                     |
| `min_prob`   | float    | —       | 0.0–1.0                                    |
| `max_prob`   | float    | —       | 0.0–1.0                                    |
| `start_date` | ISO 8601 | —       | inclusive lower bound on `timestamp`       |
| `end_date`   | ISO 8601 | —       | inclusive upper bound on `timestamp`       |

Response:

```json
{
  "logs": [
    {
      "id": "5e7e0d1f-3b8b-4c2a-9b1f-1d3c1a1e3e21",
      "transaction_id": "tx-sample-001",
      "timestamp": "2026-05-28T18:33:21.456000+00:00",
      "fraud_probability": 0.87,
      "predicted_label": 1,
      "is_fraud": true,
      "model_name": "fraud-detector",
      "model_version": "1",
      "model_stage": "Production",
      "latency_ms": 12.5
    }
  ],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

`input_features` is intentionally omitted from the list response — use `GET /v1/logs/{id}` when you need the full payload.

### GET /v1/logs/{log_id}

Returns one row including the full JSONB `input_features` payload, `optimal_threshold`, and `created_at`. `404` if the id is unknown or malformed.

```json
{
  "id": "5e7e0d1f-3b8b-4c2a-9b1f-1d3c1a1e3e21",
  "transaction_id": "tx-sample-001",
  "timestamp": "2026-05-28T18:33:21.456000+00:00",
  "fraud_probability": 0.87,
  "predicted_label": 1,
  "is_fraud": true,
  "model_name": "fraud-detector",
  "model_version": "1",
  "model_stage": "Production",
  "latency_ms": 12.5,
  "input_features": { "transaction_amount": 142.5, "merchant_category": "groceries", "...": "..." },
  "optimal_threshold": 0.5,
  "created_at": "2026-05-28T18:33:21.456000+00:00"
}
```

### GET /v1/logs/stats/summary

Aggregate counts/averages used by the future dashboard:

```json
{
  "total_predictions": 1000,
  "fraud_predictions": 45,
  "legitimate_predictions": 955,
  "fraud_rate": 0.045,
  "avg_fraud_probability": 0.21,
  "avg_latency_ms": 14.2,
  "latest_prediction_at": "2026-05-28T18:33:21.456000+00:00"
}
```

## Phase 5 Endpoint Details — Drift Detection

The drift layer compares the **reference parquet** (training snapshot from Phase 1) against the most-recent window of `prediction_logs.input_features`, using Evidently AI 0.7 (`Report(metrics=[DataDriftPreset()])`). The blueprint's `share_of_drifted_columns > DRIFT_THRESHOLD` rule is what we evaluate to decide `drift_detected` (default threshold `0.30`).

### POST /v1/monitoring/drift/check

Body (all fields optional):

```json
{ "limit": 1000, "min_samples": 200, "save_report": true }
```

Returns the run result. ``status="skipped"`` (still HTTP 200) means we did not have at least ``min_samples`` rows in ``prediction_logs`` to score:

```json
{
  "status": "complete",
  "drift_detected": true,
  "drift_score": 0.36,
  "num_drifted_features": 11,
  "total_features": 30,
  "num_samples": 1000,
  "report_id": "drift_20260528_143000_123456",
  "report_html_url": "/v1/monitoring/drift-reports/drift_20260528_143000_123456/html",
  "reason": null,
  "generated_at": "2026-05-28T14:30:00.123456+00:00"
}
```

Skipped:

```json
{ "status": "skipped", "reason": "insufficient_prediction_logs", "num_samples": 73, ... }
```

### GET /v1/monitoring/drift-reports

| Param            | Type   | Default | Notes                |
| ---------------- | ------ | ------- | -------------------- |
| `limit`          | int    | 10      | 1–100                |
| `offset`         | int    | 0       | ≥ 0                  |
| `drift_detected` | bool   | —       | filter flagged-only / clean-only |

```json
{ "reports": [<DriftReportSummary>, ...], "total": 5, "limit": 10, "offset": 0 }
```

### GET /v1/monitoring/drift-reports/latest

Returns the newest report as ``DriftReportDetail`` (404 if none yet).

### GET /v1/monitoring/drift-reports/{report_id}

Full row including `report_json`, `report_html_path`, `report_json_path`, and the window timestamps.

### GET /v1/monitoring/drift-reports/{report_id}/html

Streams the Evidently HTML artifact (`Content-Type: text/html`). 404 if the artifact is missing on disk.

### GET /v1/monitoring/stats

```json
{
  "latest_drift_score": 0.36,
  "latest_drift_detected": true,
  "last_check_at": "2026-05-28T14:30:00+00:00",
  "total_reports": 5,
  "drift_events": 2,
  "avg_drift_score": 0.21
}
```

## Phase 6 Endpoint Details — Admin + Retraining

### Authentication

All `/v1/admin/*` endpoints require an `X-API-Key` header. The expected
value is set via the `API_KEY` environment variable (default `change-me`).
Missing or wrong keys return **403 Forbidden**.

### POST /v1/admin/retrain

Triggers the Prefect retraining flow as a background task and returns
immediately.

Request:

```json
{ "trigger_reason": "manual" }
```

`trigger_reason` is one of `manual`, `drift`, or `scheduled`. Defaults to
`manual` when the body is omitted.

Response:

```json
{
  "status": "triggered",
  "trigger_reason": "manual",
  "message": "Retraining flow started"
}
```

### POST /v1/admin/reload-model

Reloads the production model from the MLflow registry into the live
FastAPI predictor singleton. Useful after a manual `make promote-model`
to skip a container restart.

Response:

```json
{
  "status": "reloaded",
  "model_name": "fraud-detector",
  "model_version": "2",
  "model_stage": "Production",
  "is_dummy": false,
  "loaded_at": "2026-05-28T14:35:00+00:00"
}
```

Returns **503** when the registry is unreachable and dummy mode is
disabled.

### POST /v1/admin/monitoring/run

Manually runs the monitoring flow once — useful for demos.

```json
{ "status": "triggered", "message": "Monitoring flow started" }
```

### GET /v1/retraining/runs

Paginated, newest-first retraining run history. Query parameters:
`limit` (1–100, default 20), `offset` (default 0), `status`
(`running`/`promoted`/`rejected`/`failed`), `trigger_reason`
(`manual`/`drift`/`scheduled`).

```json
{
  "runs": [
    {
      "id": "e9f...c4",
      "trigger_reason": "manual",
      "started_at": "2026-05-28T14:00:00+00:00",
      "completed_at": "2026-05-28T14:03:00+00:00",
      "status": "promoted",
      "challenger_run_id": "run-...-abc",
      "challenger_model_version": "2",
      "challenger_pr_auc": 0.881,
      "champion_pr_auc": 0.864,
      "promoted": true,
      "api_reload_status": "reloaded",
      "outcome_notes": "Challenger PR-AUC 0.8810 vs champion 0.8640 (delta=+0.0170, threshold>=+0.0100)"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### GET /v1/retraining/runs/latest

Returns the most recent run, or **404** when no runs have been recorded.

### GET /v1/retraining/runs/{run_id}

Returns one retraining run by UUID, or **404** when not found.

### GET /v1/retraining/stats

```json
{
  "total_runs": 5,
  "promoted_runs": 2,
  "rejected_runs": 3,
  "failed_runs": 0,
  "latest_run_at": "2026-05-28T14:00:00+00:00",
  "latest_status": "promoted"
}
```

## Phase 7 Endpoint Details — Observability

### GET /metrics

Returns the Prometheus exposition payload (`text/plain; version=0.0.4`).
Prometheus scrapes this endpoint every 15s; humans should read it via
Grafana. Excluded from the OpenAPI schema.

Custom `fraudshield_*` series exposed alongside the default
`http_*` / `process_*` metrics:

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `fraudshield_requests_total` | Counter | `method`, `endpoint`, `http_status` | Total API requests |
| `fraudshield_request_duration_seconds` | Histogram | `endpoint` | Request latency buckets (5ms → 2.5s) |
| `fraudshield_requests_in_progress` | Gauge | `endpoint` | Currently active requests |
| `fraudshield_predictions_total` | Counter | `label` (`fraud`/`legitimate`) | Predictions served, by predicted label |
| `fraudshield_prediction_score` | Histogram | — | Fraud probability buckets (0.0 → 1.0) |
| `fraudshield_batch_size` | Histogram | — | Batch-prediction sizes (1 → 100) |
| `fraudshield_model_load_timestamp` | Gauge | — | Unix epoch when current model was loaded |
| `fraudshield_model_version_info` | Gauge (=1) | `model_name`, `model_version`, `model_stage` | Current loaded model |
| `fraudshield_latest_drift_score` | Gauge | — | Most recent share-of-drifted-columns |
| `fraudshield_drift_detected_total` | Counter | — | Drift events (drift_detected=True) |
| `fraudshield_drift_checks_total` | Counter | `status` (`complete`/`skipped`/`failed`) | Drift check runs |
| `fraudshield_retraining_runs_total` | Counter | `status`, `trigger_reason` | Retraining flow runs |
| `fraudshield_latest_challenger_pr_auc` | Gauge | — | PR-AUC of latest challenger |
| `fraudshield_latest_champion_pr_auc` | Gauge | — | PR-AUC of current production champion |
| `fraudshield_model_promotions_total` | Counter | — | Successful promotion events |

Cardinality is deliberately bounded — we never push `transaction_id`,
`user_id`, or raw feature values into a label.

## Coming in Later Phases

- `GET /v1/experiments` — MLflow runs (Phase 8 frontend)
