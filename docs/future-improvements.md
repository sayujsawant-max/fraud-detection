# Future improvements

A bounded, honest backlog for FraudShield. Items are grouped by horizon
so it's clear what would ship next versus what would be a real project
of its own.

## Near-term (1–2 weeks of work)

These are additive, scoped, and don't change the architecture.

* **Per-prediction SHAP explanations.** Compute SHAP values inside the
  predictor and expose them on the `PredictionResponse`. Render the top
  three contributing features as a small bar inside `PredictionResultCard`
  on the dashboard. Adds an answer to "why was this transaction flagged?"
  that interviewers and regulators both ask.
* **Richer Recharts visualisations.** The Overview page currently shows
  rolling fraud rate and score distribution. Add: a 1-minute sliding p95
  latency curve sourced from `/metrics`, and a stacked area for
  prediction volume by `model_version` so a hot-reload event is visible.
* **Email / Slack alerting on drift events.** Webhook `POST` from the
  monitoring flow when `drift_detected=True`. A single `ALERT_WEBHOOK_URL`
  env var, optional, no new infra. Slack is the demo target; the same
  webhook shape works for Mattermost / Teams / Discord.
* **API authentication hardening.** Replace the static `API_KEY`
  comparison with a short-lived signed token (HMAC + expiry). Keep the
  `X-API-Key` ergonomics for backwards compatibility. Document the
  rotation runbook in `docs/deployment.md`.

## Medium-term (1–2 months)

These reshape the data path but don't reshape the topology.

* **Real Kaggle IEEE-CIS integration.** Swap the synthetic generator for
  the real dataset (or PaySim, depending on license). The feature schema
  stays the same; the model gets honest. Update the reference parquet
  accordingly.
* **Cloud artifact storage.** Move the MLflow artifact root from the
  bind-mounted volume to S3 / GCS / R2. The MLflow client API doesn't
  change; only `--default-artifact-root` does. Lets multiple Prefect
  workers train concurrently against a shared registry.
* **Scheduled cloud deployments.** Turn the Phase 9 CD workflow on by
  adding `GHCR_TOKEN` + `RENDER_DEPLOY_HOOK` + `VERCEL_DEPLOY_HOOK`
  secrets. Multi-arch image builds (linux/amd64 + linux/arm64) so the
  same images run on both Render and Fly.
* **Model calibration.** Add Platt scaling / isotonic regression after
  the sklearn pipeline so the fraud probabilities are well-calibrated.
  Useful for downstream rule engines that threshold on the raw score.

## Advanced (independent projects)

These would each justify a separate phase or repo.

* **Kubernetes deployment.** Helm chart with a Deployment per stateless
  service, a StatefulSet for Postgres, ConfigMap for `.env`, Secret for
  credentials, and HPA on `api` keyed off
  `fraudshield_requests_in_progress`. Swap `kube-prometheus-stack` for
  the bundled Prometheus + Grafana. See `docs/interview-guide.md` §18
  for the migration sketch.
* **Feature store.** Replace the in-API feature engineering with Feast
  (or Tecton). Push offline features for training, online features for
  serving. Reduces training-serving skew further and unlocks shared
  features across multiple models.
* **Kafka streaming ingestion.** Replace the per-request POST with a
  Kafka topic + a stateless consumer per replica. Predictions still log
  to Postgres but throughput scales linearly with consumer count.
* **Canary deployment.** Route 5 % of traffic to the challenger inside
  the API (server-side feature flag, not Istio) and emit a separate
  metric series. Promote when the canary's PR-AUC clears the gate over
  a real traffic sample, not the test set.
* **Shadow deployment.** Run the challenger alongside the champion on
  every request, log both predictions, never return the challenger's
  output. The audit table grows a `shadow_prediction` column.
* **Multi-model registry.** The fraud model is one of many. Generalise
  `MlflowRegistryClient` to handle multiple registered model names,
  multiple aliases, and a per-route mapping. Lets the same FastAPI app
  serve fraud + chargeback + KYC models from one image.
* **RBAC dashboard.** Real user accounts (OAuth via Clerk / Auth0),
  per-role views on the Settings page (analyst, ML engineer, on-call),
  per-action audit log. Out of scope for a portfolio demo, but the
  natural next thing for an actual team.

## Won't-do

Items intentionally left out so the scope stays interview-defensible:

* **A second model family** (e.g. a graph neural network) — the platform
  doesn't get more impressive by running two flavours of the same task.
* **A real fraud detection product** with chargeback feedback loops,
  human-in-the-loop review queues, etc. — that's a team-of-five
  proposition, not a single-engineer portfolio piece.
* **A custom ML framework.** Sticking to sklearn + XGBoost is the right
  call: it makes the MLOps choices the interesting part.
