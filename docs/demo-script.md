# Demo script

> A reproducible 5-minute walkthrough that proves every layer of the
> FraudShield MLOps stack works end-to-end. Useful for interviews,
> recordings, and screenshot capture.

## Before you start

Run this exact sequence in one terminal **before** opening the
recording app:

```bash
# 1. Bring up the stack
cp .env.example .env
make docker-up

# 2. Wait for services to settle (~30 s)
make docker-ps                       # all services should report "healthy"

# 3. Seed the system with realistic data
make generate-data
make train-mlflow
make promote-model VERSION=1
make db-upgrade
make seed-logs                       # 100 baseline predictions
make load-test                       # 100 demo predictions (~5 % fraud)

# 4. Sanity-check
make smoke-full                      # every endpoint should be green
```

Have these eight tabs open in this order (Cmd / Ctrl-click each link):

1. http://localhost:3000/             — Dashboard Overview
2. http://localhost:3000/predict      — Predict page
3. http://localhost:3000/logs         — Prediction logs
4. http://localhost:3000/monitoring   — Drift monitoring
5. http://localhost:3000/settings     — Admin actions
6. http://localhost:5000/             — MLflow runs
7. http://localhost:4200/             — Prefect flows
8. http://localhost:3001/             — Grafana dashboards (admin / admin)

---

## 00:00 – 00:30 — Introduce the project

> "FraudShield is a production-grade MLOps platform I built end-to-end.
> Not a notebook — a system. It serves an XGBoost fraud detector through
> FastAPI, logs every prediction to PostgreSQL, runs Evidently AI for
> drift detection, automates retraining through Prefect, and is
> instrumented with Prometheus and Grafana. It's all wrapped in a Next.js
> dashboard. Everything runs locally with one Docker Compose command."

(On screen: the architecture diagram from `docs/architecture.md` §2,
or the README hero.)

## 00:30 – 01:00 — Architecture + stack

> "Six layers. Data: a Postgres backing store and a synthetic fraud
> dataset. Training: sklearn pipeline tracked in MLflow with a model
> registry. Serving: FastAPI loads the production-aliased model from the
> registry. Monitoring: Evidently compares the live distribution against
> a training-time reference. Orchestration: Prefect drives the monitoring
> cron and the retraining flow. Observability: Prometheus scrapes the
> API's `fraudshield_*` metrics and Grafana renders four dashboards."

(On screen: `docs/architecture.md` Mermaid diagram.)

## 01:00 – 01:45 — Predict a fraud transaction

Switch to **/predict** tab.

> "Here's the dashboard's Predict page. I'll load the high-risk fraud
> example — foreign country, late-night cash advance, brand-new account,
> previous fraud flag."

Click **Load High-Risk Fraud** → **Score transaction**.

> "We get back a fraud probability — call out the percentage — a HIGH
> RISK badge, the model version that scored it, latency under 50 ms, and
> the transaction ID. The decision says BLOCK because the score is above
> our optimal threshold."

(Capture: `predict-page.png`.)

## 01:45 – 02:15 — Audit trail + API docs

Switch to **/logs** tab.

> "Every prediction the API serves lands in a Postgres `prediction_logs`
> row. The Logs page is the audit surface. The top row is the
> transaction I just submitted — click it."

Click the row → drawer opens with `input_features` JSON.

> "Full feature payload, the model that scored it, the threshold it used.
> This is what makes drift detection possible later — we have the input
> distribution captured permanently."

(Capture: `logs-detail.png` optional.)

Briefly open http://localhost:8001/docs:

> "And here's the API itself — auto-generated OpenAPI docs."

## 02:15 – 02:45 — MLflow

Switch to **MLflow** tab.

> "Every training run is tracked in MLflow. Three model families per
> run — logistic regression, random forest, XGBoost — with PR-AUC,
> ROC-AUC, F1, optimal threshold, the full sklearn pipeline as an
> artifact, and the registry version aliased `champion` and `production`."

(Capture: `mlflow-runs.png` — the experiment view with the champion
ribbon on the winning row.)

## 02:45 – 03:30 — Seed drift + run the check

Back in a terminal:

```bash
make seed-drift                      # 500 rows with shifted distributions
```

Switch to **/monitoring** tab. Click **Run drift check**.

> "Phase 5 — drift detection. I just seeded 500 predictions whose feature
> distributions are shifted relative to training. The dashboard fired the
> Evidently report, which compared the live window against the reference
> parquet. Result: drift detected, drift score above the 0.30 threshold,
> 20-plus features flagged."

(Capture: `monitoring-page.png`.)

## 03:30 – 04:00 — Evidently report

Click the **Open HTML ↗** link on the freshest drift row.

> "The full Evidently report is served straight from the backend. Per-
> column drift, the reference vs current distributions, statistical
> tests — this is the operator-facing forensic surface."

(Capture: `evidently-report.png` optional.)

## 04:00 – 04:30 — Trigger retraining + Prefect

Switch to **/settings** tab.

> "Drift is detected — in production the monitoring flow would call the
> retraining flow automatically. Let me trigger it manually here to keep
> the demo deterministic."

Enter `change-me` in the API key field → **Save** → **Run Retraining Flow**.

Switch to the **Prefect** tab:

> "Prefect picks up the flow run. It trains an XGBoost challenger,
> compares its PR-AUC to the current champion's, and either promotes it
> or rejects it. The promotion gate is one PR-AUC point of improvement —
> `MODEL_PROMOTION_MIN_DELTA=0.01`."

(Capture: `prefect-flow.png` — the deployments view + a running flow.)

## 04:30 – 05:00 — Grafana + close

Switch to the **Grafana** tab. Open **FraudShield → Model Behavior**.

> "Finally — observability. Prometheus is scraping every 15 seconds and
> Grafana renders the result. This dashboard shows the prediction
> volume, fraud rate, score distribution as a heatmap, and the currently-
> loaded model version. There are three more dashboards for API
> performance, drift + retraining, and system health."

(Capture: `grafana-dashboard.png`.)

> "The complete MLOps loop, observable end-to-end, in one local stack.
> Every layer is a separate service so the next step — Kubernetes — is
> mechanical. Thanks for watching."

(Stop recording.)

---

## Screenshot checklist

If you're capturing for the README rather than recording, snap these
seven into `docs/assets/screenshots/`:

| File | Tab / page | Required state |
| --- | --- | --- |
| `dashboard-home.png` | Dashboard Overview | Non-zero KPIs (run `make load-test` first) |
| `predict-page.png` | /predict | After scoring the high-risk fraud example |
| `monitoring-page.png` | /monitoring | After running `make seed-drift && make drift-check` |
| `mlflow-runs.png` | MLflow | After `make train-mlflow && make promote-model VERSION=1` |
| `prefect-flow.png` | Prefect UI | After `make deploy-prefect-flows` |
| `grafana-dashboard.png` | Grafana Model Behavior | After `make load-test` |
| `architecture.png` | Mermaid export | See `docs/assets/architecture-diagram.md` |

See [`docs/assets/README.md`](assets/README.md) for filename + sizing
conventions.
