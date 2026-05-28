# Interview Guide

> Twenty questions an interviewer will actually ask about FraudShield,
> with the answer that lands well in five minutes or less. Use this as
> the script behind the demo — the dashboard shows *what*, this doc
> explains *why*.

## 1. What problem does FraudShield solve?

Credit-card fraud teams need three things at once: a fast scoring API
they can call inline at checkout, a durable audit trail of every score,
and a way to know *when the model is getting worse* before it actually
costs them. Most ML projects ship the first thing and stop. FraudShield
ships all three — plus the retraining loop that closes the model-decay
gap automatically.

## 2. Why is this more than a notebook project?

A notebook proves the model can be trained. FraudShield proves the
*model lifecycle* can be operated: trained, registered, served,
audited, monitored for drift, retrained on drift, promoted only when it
beats the champion, hot-reloaded into the live API, and observed in real
time. Each of those verbs is a separate phase backed by tests and
infrastructure. Seven production-equivalent services in one Docker
Compose file is what makes it a *system*.

## 3. Why FastAPI?

Async-native (so a `predict` and an audit-log write don't block each
other), Pydantic v2 validation (so the API contract is enforceable, not
documented), built-in OpenAPI docs (so `/docs` is the spec), and a
small enough surface that adding the Prometheus instrumentator + a
custom middleware is a couple of lines. Compared to Flask + Marshmallow
+ Flask-RESTX we save 30 % of the boilerplate.

## 4. Why MLflow?

It's the only OSS registry that does experiment tracking *and* a model
registry *and* native sklearn pipeline logging *and* talks SQL natively
— so I can stand it up against the same Postgres I already need. The
alternative (Weights & Biases for tracking + Sagemaker / Vertex for
serving) couples the project to a paid cloud. MLflow keeps it free and
self-hostable.

## 5. Why PR-AUC instead of accuracy?

Fraud is imbalanced — roughly 5 % positive class in the synthetic
dataset, often <1 % in production data. Accuracy is dominated by the
majority class: a "predict legit" stub scores 95 %. PR-AUC measures
performance on the positive class specifically and rewards a model that
gets the precision-recall trade-off right on the small fraction we
actually care about. Same reason we use `scale_pos_weight` on XGBoost
rather than oversampling.

## 6. How do you avoid training-serving skew?

The sklearn `Pipeline` (preprocessor + classifier) is logged as a
*single* MLflow artifact via `mlflow.sklearn.log_model`. The FastAPI
serving layer loads that exact same pipeline and calls `predict_proba`
on it. There's no second copy of the preprocessing code in the API. The
input contract is the Literal-typed `TransactionRequest` schema — and
the categorical Literals are derived from
`backend/src/features/constants.py`, the same module the training code
imports. So the API will reject a value the training pipeline never
saw at parse time, not at predict time.

## 7. What is data drift?

The distribution of features at serving time has moved away from the
distribution at training time. The model wasn't trained on the new
shape, so its predictions become unreliable — usually subtly, before
the precision visibly tanks. Drift can be feature-level (one column
shifts: a new merchant category onboards) or covariate (joint
distribution shifts: weekend traffic flips to weekday). FraudShield
measures both via Evidently's `DataDriftPreset`.

## 8. How does Evidently detect drift?

I save a 5 000-row snapshot of the training set as
`reference.parquet`. On each drift check, I pull the last
`DRIFT_LOOKBACK_LIMIT` prediction-log rows from Postgres, reconstruct
the feature DataFrame, and call `Report(metrics=[DataDriftPreset()])`.
Evidently runs per-column statistical tests (K-S for numerical, χ² for
categorical) and returns a share-of-drifted-columns score. If the
score exceeds `DRIFT_THRESHOLD` (0.30 by default), drift is flagged.
The full HTML report is saved next to the database row so a human can
audit *which* columns moved.

## 9. How does Prefect automate retraining?

Two flows: `monitoring_flow` runs on a 6-hour cron and calls the same
drift check the dashboard exposes. When it returns
`drift_detected=True`, it calls `retraining_flow(trigger_reason="drift")`
directly. The retraining flow can also be triggered manually via
`POST /v1/admin/retrain` (API-key-protected) or on the weekly schedule
`PREFECT_RETRAINING_CRON`. Each flow run records a `retraining_runs`
row capturing the trigger, status, both PR-AUCs, and outcome notes.

## 10. How does champion/challenger promotion work?

1. Train an XGBoost challenger inside an MLflow run.
2. Register it as a new version of `fraud-detector` and alias it
   `champion`.
3. Read the current `production` model's PR-AUC from MLflow.
4. Promote only when
   `challenger_pr_auc - champion_pr_auc >= MODEL_PROMOTION_MIN_DELTA`
   (0.01 by default — one PR-AUC point).
5. On promotion: flip the `production` alias, tag old versions
   `Archived`, and `POST /v1/admin/reload-model` so the live API picks
   up the new champion *without* a container restart.
6. Either way, log the outcome to `retraining_runs`.

If there's no champion (first-ever run), the challenger auto-promotes
with an explanatory note. If the comparison can't be made (champion has
no PR-AUC metric), the run is rejected — we don't promote blind.

## 11. Why log predictions to PostgreSQL?

Three reasons: (1) it's the audit trail regulators and security teams
will want; (2) it's the *input* to the drift detector — Evidently needs
the served distribution, which is exactly what these rows record; (3)
it's the data the dashboard's `/logs` page renders so operators can
inspect any individual decision. Postgres' JSONB column type lets us
store the full `input_features` payload without flattening it, which
matters when the feature schema changes between model versions.

## 12. What does Prometheus monitor?

Fifteen `fraudshield_*` collectors covering five families:

* **Request** — `requests_total{method,endpoint,http_status}`,
  `request_duration_seconds_bucket{endpoint}`,
  `requests_in_progress{endpoint}` (the classic Rate/Error/Duration triad)
* **Predictions** — `predictions_total{label}`, `prediction_score`
  histogram, `batch_size` histogram
* **Model metadata** — `model_load_timestamp`,
  `model_version_info{model_name,model_version,model_stage}`
* **Drift** — `latest_drift_score`, `drift_detected_total`,
  `drift_checks_total{status}`
* **Retraining** — `retraining_runs_total{status,trigger_reason}`,
  `latest_challenger_pr_auc`, `latest_champion_pr_auc`,
  `model_promotions_total`

Cardinality is bounded by design — no `transaction_id` or `user_id` in
any label.

## 13. What does Grafana show?

Four auto-provisioned dashboards in the `FraudShield` folder:

* **API Performance** — request rate, p50/p95/p99 latency, error rate,
  in-progress gauge.
* **Model Behavior** — total predictions, fraud rate %, score
  distribution heatmap, batch-size heatmap, current model version table.
* **Drift & Retraining** — latest drift score gauge with the 0.30
  threshold marked, drift events counter, retraining status barchart,
  champion vs challenger PR-AUC trend.
* **System Health** — `up{job="fraudshield-api"}`, scrape duration,
  model load timestamp formatted as a human date, 5xx rate.

Anyone can answer "is the system healthy, is the model behaving, is
drift creeping up, did retraining run?" in under thirty seconds.

## 14. How would you scale this system?

Three axes:

* **Horizontal** — the API is stateless once the model is loaded. Run
  N replicas behind a load balancer, each with its own MLflow client.
  An HPA keyed off `fraudshield_requests_in_progress` is the natural
  trigger.
* **Async log writes** — the prediction log write is already async and
  best-effort. Behind a real load it becomes a Kafka topic + a stateless
  consumer that batches into Postgres. The API path stops touching the
  DB at all.
* **Artifact storage** — move MLflow's `--default-artifact-root` from
  the bind-mounted volume to S3 / GCS / R2 so multiple workers can
  train concurrently without lock contention.

The bottleneck is *not* the model — XGBoost predict_proba is well
under a millisecond per row. It's the log write and the cold-start
model load, and both have known fixes above.

## 15. How would you deploy this in production?

See `docs/deployment.md` for the full checklist. Short version:

* **Frontend** → Vercel (Next.js standalone build, env var
  `NEXT_PUBLIC_API_URL`).
* **Backend + Postgres + MLflow** → Render (three services, internal
  DNS).
* **Prefect** → Prefect Cloud (free tier; one `PREFECT_API_KEY` env var
  is all the API needs).
* **Prometheus + Grafana** → either Grafana Cloud free tier or keep
  local for the demo and screenshot the dashboards.
* **CI/CD** → the workflow files (`ci.yml` + `cd.yml`) are already
  written. Adding `GHCR_TOKEN`, `RENDER_DEPLOY_HOOK`, and
  `VERCEL_DEPLOY_HOOK` to repo secrets enables the deploy step; no
  code change.

The Phase 9 cost estimate (Render free + Vercel free + Prefect Cloud
free) is $0/month for a portfolio demo.

## 16. What are the limitations?

Honest list:

* **Synthetic data.** The pipeline is real, the labels aren't. A real
  deployment would swap the generator for Kaggle IEEE-CIS or live
  traffic.
* **Single-model registry.** One challenger per retrain, no shadow or
  canary against live traffic.
* **No per-prediction explainability.** SHAP is a known next step.
* **No alerting routing.** Prometheus has the metrics, but there's no
  Alertmanager → Slack wired up yet.
* **Static admin key.** Acceptable for a portfolio; production needs
  signed tokens with rotation.
* **One MLflow instance.** Fine for one team; multi-tenant would need
  S3 artifacts + per-experiment ACLs.

## 17. What would you improve next?

In priority order: SHAP explanations on `PredictionResponse`, then
real Kaggle data, then cloud artifact storage, then Alertmanager →
Slack. The full backlog with horizons (near / medium / advanced) is in
[`docs/future-improvements.md`](future-improvements.md).

## 18. How would Kubernetes fit later?

Docker Compose already does the structural work — each service is
independently containerised, talks over a well-known DNS name, has a
healthcheck, and stores state in a named volume. The K8s migration is
mechanical:

1. One Deployment per stateless service (`api`, `frontend`,
   `prefect-flows`) with the Compose healthcheck as
   `readinessProbe` / `livenessProbe`.
2. StatefulSet + PVC for Postgres.
3. Helm chart or Kustomize overlay turning `.env` keys into a ConfigMap
   and `*_PASSWORD` / `API_KEY` into a Secret.
4. HPA on the API Deployment keyed off
   `fraudshield_requests_in_progress` — exactly the custom metric Phase
   7 emits.
5. `kube-prometheus-stack` replaces the bundled Prometheus + Grafana
   with the same scrape config and dashboard JSON.

Nothing in the app changes. That's the design goal: the Compose stack
is the dev-time stencil for the K8s deployment.

## 19. How would you handle real user security?

Today the only auth surface is `X-API-Key` on `/v1/admin/*`. For real
users I'd layer:

* **OAuth via Clerk or Auth0** for human accounts on the dashboard.
* **Short-lived JWT** instead of the static `API_KEY` for admin
  endpoints; rotate via env-var.
* **RBAC** — three roles (analyst / ML engineer / on-call) gating which
  parts of `/settings` are usable.
* **Audit log on the audit log** — every admin action lands in a
  separate `admin_actions` table with the actor, time, IP, payload.
* **mTLS between services** in the K8s deployment, so a leaked API key
  alone isn't sufficient to reach Postgres or MLflow.
* **Secrets** in Vault or the cloud provider's KMS, not env vars on
  disk.

Out of scope for a portfolio demo, but documenting the answer
proactively is what shows you'd actually own this in production.

## 20. What did you learn from this project?

Three things I'd call out in an interview:

* **The hardest part of MLOps isn't the ML.** It's the seven services
  that need to talk to each other, the failure modes between them, and
  the tests that prove the integration. Phase 9's testing strategy —
  every test uses in-memory SQLite + a `DummyFraudModel` + monkey-
  patched Prefect tasks — was the single biggest unlock for shipping
  fast.
* **Observability is a design decision, not a feature.** Adding
  Prometheus *after* the API was built would have been ten times
  harder; baking the `fraudshield_*` namespace in alongside the routers
  let me write Grafana dashboards as I built them.
* **Backwards-compatible additivity is what lets a project this size
  ship.** Each phase added to the system without rewriting prior
  layers. Phase 8 (Next.js) consumed Phase 6's APIs unchanged; Phase 7
  (Prometheus) didn't require touching Phase 5's drift code. That
  discipline is what makes the codebase navigable months later.

---

See `FRAUDSHIELD_BLUEPRINT.md` §10 for the canonical short-form
answers, and `docs/demo-script.md` for the live-demo version of all
this.
