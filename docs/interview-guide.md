# Interview Guide

> **Status:** Placeholder — answers refined as each phase ships.

This is the speaking-points companion to FraudShield MLOps. Use this when prepping for ML/MLOps/AI engineer interviews.

## Questions

### 1. Walk me through the project

Coming in Phase 9.

### 2. Why XGBoost for fraud detection?

Fraud is a tabular, highly class-imbalanced problem (~4–5% positives) with non-linear feature interactions (late-night + foreign + high-velocity is much riskier than the sum of its parts). XGBoost handles all three:

- Gradient-boosted trees capture those interactions without manual crosses.
- `scale_pos_weight = N_neg / N_pos` re-weights the loss so the minority class actually matters during training.
- We select on **PR-AUC**, not ROC-AUC, because on imbalanced data ROC-AUC overstates how good a model is — the negative class dominates the false-positive rate even when precision is poor. PR-AUC focuses on the trade-off that operations actually cares about: how many flagged transactions are real fraud.

### 2a. What does the MLflow integration give you?

- **Reproducibility.** Every training run is one MLflow run with params (model type, hyperparameters, `feature_set_version`, `dataset_version`, fraud rate, seed), metrics (`pr_auc`, `roc_auc`, `f1_score`, `optimal_threshold`, `training_duration_seconds`), artifacts (`confusion_matrix.json`, `classification_report.txt`, `feature_names.json`, `optimal_threshold.json`, `model_summary.json`), and the full sklearn `Pipeline` (preprocessor + classifier) logged as a single artifact. Anyone can rerun a champion by ID.
- **No training–serving skew.** We log the whole `Pipeline` — not just the estimator — so Phase 3 FastAPI calls `mlflow.sklearn.load_model(...)` and applies the exact same imputers / scalers / ordinal encoders that ran at training time.
- **Registry as the deploy contract.** The champion is registered as `fraud-detector`. Promotion to "Production" is an alias flip — MLflow 3.x removed Stages, so we use the `production` alias and a `stage` tag for human readability. A deploy = a registry call, no rebuild. Phase 5's auto-retrain flow trains a challenger, compares PR-AUC, and only flips the alias if the challenger wins.
- **Champion selection by PR-AUC** rather than ROC-AUC for the same reason as model choice — it reflects the actually-imbalanced production reality.

### 2b. Why FastAPI for the serving layer?

- **Async I/O + ASGI.** Prediction handlers don't block on logging, MLflow client roundtrips, or future PostgreSQL inserts (Phase 4) — uvicorn dispatches each request on the event loop. The synchronous sklearn `.predict_proba` call is the only piece that holds the loop, and at 10–15 ms per row that's effectively free for a single-instance prototype.
- **Pydantic v2 validation as a contract.** Every `POST /v1/predict` body is validated against `TransactionRequest` before the predictor ever sees it. Range checks (`transaction_amount > 0`, `ip_risk_score ∈ [0, 1]`), `Literal` enums for the five categoricals, and `extra='forbid'` to reject unknown fields. A bad request becomes a clean 422 with the failing field path — the model never has to defend itself against garbage input.
- **OpenAPI for free.** `/docs` and `/openapi.json` are generated from the schemas, so the frontend (Phase 7) and any external consumer get a typed client without us writing one.
- **Observability primitives.** `prometheus-fastapi-instrumentator` exposes `/metrics` for free, the lifespan hook is the natural place to load the MLflow model at startup, and `Depends(get_predictor)` makes the predictor mockable in tests.

### 2c. Why bundle the whole preprocessing pipeline into the MLflow artifact?

The number-one source of model bugs in production is *training-serving skew*: feature engineering done one way in the notebook, a slightly different way in the API. We avoid it by logging the full `Pipeline(preprocessor, classifier)` — including `SimpleImputer`, `RobustScaler`, and `OrdinalEncoder` — as the MLflow artifact. The API does exactly one thing: build a DataFrame from the request body and call `pipeline.predict_proba`. The same imputers, the same scalers, the same encoder mapping that saw `groceries` at training time see `groceries` at serving time. There is no separate "serving preprocessor" to drift out of sync.

The Pydantic `Literal` types for the categorical fields are also generated from `src/features/constants.py`, the same list the synthetic generator uses. If a developer adds a new merchant category, every layer — generator, encoder, schema — updates in one place.

### 2d. How does the API load the Production model?

At FastAPI startup the lifespan hook calls `load_model(settings)`. The loader walks three URIs in order:

1. `models:/fraud-detector/Production` — legacy MLflow 2.x stage taxonomy.
2. `models:/fraud-detector@production` — MLflow 3.x alias (the canonical one for us, since 3.x removed stages).
3. `models:/fraud-detector@champion` — fallback used when training has registered a model but it has not been promoted yet.

For the threshold it looks at the run's `optimal_threshold.json` artifact first (most authoritative — written by training itself), then the run-level `optimal_threshold` metric, then `DEFAULT_THRESHOLD` from settings. The resulting `LoadedModel` is wrapped in a `FraudPredictor` and stashed on `app.state` so `Depends(get_predictor)` can hand it to every router.

If every resolution attempt fails:
- with `ALLOW_DUMMY_MODEL=true`, a deterministic `DummyFraudModel` is substituted so local dev / CI still work;
- with `ALLOW_DUMMY_MODEL=false`, the predictor is left `None` and `/ready` returns 503 — Kubernetes / Prometheus / Docker healthchecks can then divert traffic until the registry is fixed.

### 2e. Why prediction logging? Why PostgreSQL? Why JSONB?

Three reasons logging matters on day one, not as a Phase-9 nice-to-have:

1. **Audit trail.** Fraud is high-stakes — a flagged customer can call support and we need to be able to explain exactly *which* model version + threshold + feature values produced the decision. The `prediction_logs` table is that source of truth, written transactionally so we can't return a 200 without a row landing in storage.
2. **Drift detection in Phase 5.** Evidently needs a recent prediction window to compare against the reference distribution. Storing the raw input features (not just the prediction) is what lets the drift flow run any feature-level statistic without going back to the API.
3. **Operational debugging.** "Why did the predicted-fraud rate spike at 03:00?" is a question you can only answer with a query, not log scraping. `SELECT predicted_label, COUNT(*) FROM prediction_logs WHERE timestamp > now() - interval '1 hour' GROUP BY 1;` is one statement; greping JSON logs across N pods isn't.

**PostgreSQL** for storage because the project already runs Postgres (MLflow backend) and we don't want a second stateful service just for logs. SQLAlchemy 2.0 async + Alembic migrations gives us strict schema evolution. **JSONB** for `input_features` because:
- the feature set evolves between phases (Phase 1 had 28 columns, we'll add explanation features in Phase 5), and re-running ALTER TABLE on every change is operationally painful;
- Postgres can `GIN`-index JSONB so the Phase 5 drift queries (`WHERE input_features->>'merchant_category' = 'crypto_exchange'`) stay efficient;
- the Phase 7 frontend can render whatever fields the model used, with no API schema change required when training adds a feature.

We keep the *high-cardinality, query-heavy* columns (`fraud_probability`, `predicted_label`, `model_version`, `timestamp`) as first-class typed columns so the obvious analytics queries don't pay the JSONB tax.

### 2f. Why prediction should not fail if audit logging fails

The contract on `/v1/predict` is *score the transaction*. A scored transaction has business value even if we couldn't write the audit row — the call site can authorise or block on the response. Crashing the request because Postgres had a brief blip would invert the dependency: the user-facing API would now require the database to be up just as much as the model.

So Phase 4 logs are **best-effort**:
- the prediction runs first;
- the response is computed before we touch the DB;
- the repository write is wrapped in a `try/except Exception` that logs with Loguru and swallows;
- the integration test `test_predict_succeeds_even_if_logging_fails` enforces this contract with a mocked-failure path.

The trade-off is that a brief Postgres outage produces a gap in the audit trail. We accept that — it's recoverable from upstream MLflow / application logs and far cheaper than a serving outage. Phase 5 will add an outbox-style queue if the gap turns out to matter.

### 3. How does your drift detection work?

**What drift is, in one sentence:** the live transaction distribution stops looking like what the model was trained on, so the model's predictions stop being trustworthy.

**Why this matters for fraud specifically:** fraud patterns evolve adversarially. A model trained on "January 2026" card-not-present fraud will under-perform on April-2026 traffic when attackers shift to a new merchant category, a new device fingerprint, or a new amount range. Static models silently degrade — the predictions still return 200, the probabilities still look plausible, but the precision-at-fixed-recall collapses. Drift detection is the canary that fires *before* the chargeback rate confirms it.

**How FraudShield computes it (Phase 5):**

1. **Reference dataset.** The training-time parquet saved during Phase 1 (`backend/data/reference/reference.parquet`) is the baseline. We deliberately *don't* recompute the baseline from rolling production traffic — that would let the baseline drift along with the data and mask any real shift.
2. **Current window.** The most recent `DRIFT_LOOKBACK_LIMIT` (default 1000) rows of `prediction_logs.input_features` — the JSONB column populated by Phase 4. The data flow is `serve → write JSONB → query JSONB → score drift`, which is why Phase 4 had to land first.
3. **Evidently AI.** `Report(metrics=[DataDriftPreset()])` runs per-column statistical tests (K-S for numeric, Z-test for categorical) and produces a `DriftedColumnsCount` headline metric whose `value.share` is "share of drifted columns". Per-column drift values are kept in the JSON for the frontend to render later.
4. **Threshold.** We flag drift when `share_of_drifted_columns > DRIFT_THRESHOLD` (default `0.30`). The threshold is **configurable via env** — different teams tolerate different false-positive rates, and the right value depends on how often you can afford to retrain. 0.30 is the blueprint default and matches Evidently's own conservative recommendation for fraud-like distributions.
5. **Insufficient data is "skipped", not "failed".** When fewer than `DRIFT_MIN_SAMPLES` (default 200) rows are available we return `status="skipped"` rather than running on a tiny window — small-sample drift tests are too noisy to act on and would generate alert fatigue.

**Persistence:** every run writes (a) an HTML artifact under `DRIFT_REPORT_DIR` for the frontend to embed, (b) a JSON artifact for machine consumption, and (c) a `drift_reports` row capturing the headline metrics, the window timestamps, and the artifact paths. The row is what Phase 6's Prefect monitoring flow will query to decide whether to call the retraining flow.

### 3a. Why share_of_drifted_columns > 0.30 (and why is it configurable)?

A single drifted column doesn't mean the model is broken — feature distributions wobble for benign reasons (a new merchant category onboards, a marketing push shifts the amount mix). The blueprint uses `share_of_drifted_columns` as a coarse aggregate so we only trigger when *several* columns moved together — that's the pattern of a regime shift, not a single benign change.

0.30 was chosen because the fraud feature set has ~29 columns; 0.30 × 29 ≈ 9 columns drifting simultaneously, which is approximately the right "this is a regime change, not noise" threshold for the synthetic generator. Real production teams tune this number empirically — you want few enough false positives that on-call doesn't get paged daily, but few enough false negatives that a real drift event triggers retraining within a useful window. Keeping it in `Settings.DRIFT_THRESHOLD` (not hardcoded) is what lets that tuning happen without a code deploy.

### 3b. How Phase 5 prepares for Phase 6 Prefect automation

Phase 5 is intentionally synchronous and manual — `POST /v1/monitoring/drift/check` and `python scripts/run_drift_check.py` are the two triggers. We did the heavy design work (loader → detector → store → repository) so Phase 6 can wrap exactly the same building blocks in a Prefect flow:

* The Prefect `monitoring_flow` will call `load_reference_dataset` + `build_current_dataset` + `run_drift_detection` on a 6-hour cron.
* When the resulting `DriftDetectionResult.drift_detected` is True, the flow will call the `retrain_flow` (also Phase 6), which trains a challenger, compares PR-AUC, and flips the MLflow alias if the challenger wins.
* The `drift_reports.triggered_retrain` boolean is already in the schema specifically to record that handoff.

Splitting it this way means Phase 5 is shippable on its own (we have monitoring and a human-driven retrain story), and Phase 6 is purely automation glue — no new ML logic.

### 4. What does Prefect do in this project? (Phase 6)

Prefect is the orchestrator that turns the manual drift check and manual retrain script from Phase 5 into an automated MLOps loop. Two flows are defined in `backend/src/workflows/`:

* **`monitoring_flow`** — runs every 6 hours on a Prefect cron schedule. Re-uses the Phase 5 loader/detector/store building blocks, persists a `drift_reports` row, and — when `drift_detected=True` — calls the retraining flow directly.
* **`retraining_flow`** — trains a *challenger* XGBoost model on the current train/test splits, fetches the *champion* PR-AUC from MLflow, and either promotes the challenger (if the PR-AUC delta meets `MODEL_PROMOTION_MIN_DELTA`) or rejects it. Either way it writes a `retraining_runs` audit row.

### 5. How does champion/challenger comparison work?

1. **Train the challenger.** The retraining flow trains the same XGBoost pipeline as Phase 2 inside its own MLflow run, registers it under the `fraud-detector` model name, and tags it `role=challenger`.
2. **Read the champion's PR-AUC.** `get_champion_metrics_task` resolves the version currently aliased `production` (or `champion` as a fallback) and reads its `pr_auc` metric back out of the MLflow run.
3. **Compare with a hard threshold.** `compare_challenger_to_champion_task` returns `should_promote=True` only when `challenger_pr_auc - champion_pr_auc >= MODEL_PROMOTION_MIN_DELTA` (default 0.01). PR-AUC is the right metric here — it's the same imbalanced-data choice we made in training (§9 of the blueprint).
4. **Promote or reject.** If promotion wins, the production alias flips, old versions are tagged `Archived`, and the API is hot-reloaded via `POST /v1/admin/reload-model`. If not, the run is marked `rejected` and the champion stays.

The "first model ever trained" case is handled explicitly: when no production champion exists yet, the challenger is auto-promoted with a log note (`No champion found; promoting first trained model.`).

### 6. Why a PR-AUC improvement threshold instead of just "challenger > champion"?

Because PR-AUC is noisy on a finite test set — a 0.001 improvement is well within sample variance. Without a floor, you'd get a promotion churn where every retrain ping-pongs the production alias for no real quality gain. `MODEL_PROMOTION_MIN_DELTA=0.01` (one PR-AUC point) is a conservative floor that says "demand a meaningful improvement before we re-version production". Tunable via env so the team can tighten or loosen it without a code deploy.

### 7. What happens if a challenger is rejected?

* The MLflow run is still registered as a new model version (so we have its weights, metrics, and artifacts for postmortem analysis).
* The `production`/`champion` alias does **not** move.
* The `retraining_runs` row is closed with `status="rejected"`, both PR-AUCs recorded, and `outcome_notes` carries the comparison summary string for the dashboard.
* The API keeps serving the same champion — no reload is triggered.

This is the right default: we'd rather under-promote than over-promote on a noisy run, and the audit row gives us forensic value either way.

### 8. Why Prometheus and Grafana? (Phase 7)

Prometheus is the de-facto standard pull-based metrics database for cloud-native services — every K8s, EKS, GKE, Render, and Fly.io stack already speaks it, every alertmanager integrates with it, and the storage model is purpose-built for the time-series shape that ML serving actually produces (request rates, latency histograms, error counts, slow-moving model gauges). Grafana sits on top of Prometheus as the visualization layer; the two ship together so often they're effectively a single stack. Choosing them is what makes this project deployable into any production environment without re-instrumenting the API.

### 9. What metrics does FraudShield track and why?

Five families, all under the `fraudshield_*` namespace:

* **Request metrics** (`requests_total`, `request_duration_seconds`, `requests_in_progress`) — the standard RED triad (Rate, Error, Duration). Lets us answer "is the API healthy?" without looking at logs.
* **Prediction metrics** (`predictions_total{label}`, `prediction_score`, `batch_size`) — the model-behavior view. We can see fraud rate over time, score distribution shifts, and whether batch traffic looks like prod or backfill.
* **Model metadata** (`model_version_info`, `model_load_timestamp`) — answers "which version is live, and when did it last reload?". A flapping load timestamp is a fast canary for a crash loop.
* **Drift metrics** (`latest_drift_score`, `drift_detected_total`, `drift_checks_total{status}`) — fuses the Phase 5 Evidently output into the observability stack so the drift gauge shows up next to API latency on the same dashboard.
* **Retraining metrics** (`retraining_runs_total{status,trigger}`, `latest_challenger_pr_auc`, `latest_champion_pr_auc`, `model_promotions_total`) — the closed-loop signal that the auto-retraining flow from Phase 6 is actually running, training challengers, and (sometimes) promoting them.

### 10. Why avoid high-cardinality labels?

Every unique label combination is a separate time-series in Prometheus' inverted index, and the index sits in RAM. Pushing `transaction_id` or `user_id` into a label would explode that index — millions of series, hundreds of GB of RAM, scrape failures, and a Prometheus that falls over the moment traffic ramps. So in FraudShield the only labels on counters/histograms are bounded values we control: HTTP method, route template, status code, predicted label (`fraud`/`legitimate`), retraining status, trigger reason. Anything per-request stays in the prediction log and drift report tables — the audit trail, not the metric.

### 11. How does this prove production ML readiness?

The system answers the four questions every on-call team needs to answer in under 30 seconds: "is the API up?", "is it serving real predictions or junk?", "has the model degraded?", "did the auto-retrain loop actually do something?". Phase 7's four dashboards each pick one of those questions and lay out the metrics that answer it. No log digs, no SQL queries — just open the dashboard. That's the gap between a notebook and a production system.

### 12. How does monitoring connect to drift and retraining?

The same metrics carry the closed loop end-to-end:

1. Predictions stream in → `predictions_total` and `prediction_score` move on the **Model Behavior** dashboard.
2. The Phase 5 drift detector runs on schedule (Phase 6 monitoring flow) → `latest_drift_score` and `drift_checks_total` move on the **Drift & Retraining** dashboard.
3. If drift crosses threshold the retraining flow fires → `retraining_runs_total{status="running"}` ticks, then `…{status="promoted"|"rejected"}` lands.
4. On a promotion `model_promotions_total` ticks and `model_version_info` swings to the new version on the dashboard, confirming the closed loop closed.

That's the full MLOps story visible in one screen — exactly the demo for an interviewer.

### 13. How would you scale this to production traffic?

Coming in Phase 9.

### 14. How would you demo the Next.js dashboard? (Phase 8)

Recommended 5-minute interview demo path:

1. **Open Overview at http://localhost:3000** — call out the KPI strip (total predictions, fraud rate, latest drift, retraining outcomes) and the live "API online" badge in the topbar. This is the "is the system healthy?" frame.
2. **Click Predict** — switch the form to "Load High-Risk Fraud Example" and submit. The PredictionResultCard renders a large fraud probability, a red HIGH RISK badge, the model version + latency, and the BLOCK/ALLOW decision. Then click "Load Legit Example" and submit again to show the model's other extreme.
3. **Click Logs** — the prediction we just submitted is the newest row. Click into it to open the detail drawer with the full input_features JSON. Filter by predicted_label=fraud to demonstrate server-side filtering.
4. **Click Monitoring** — show the latest drift score gauge + report table. Click "Run drift check" to fire the Phase 5 detector. The "Open HTML" link on any row jumps into the Evidently report embedded straight from the backend.
5. **Click Experiments** — explain that the dashboard surfaces the retraining-runs audit table directly, and link out to MLflow for deeper per-run drill-down (artifacts, params, model URI).
6. **Click Settings** — enter the API key, set trigger reason = manual, and click "Run Retraining Flow". A second tab on the same page shows the run progressing through running → promoted/rejected. The "Reload Model" button hot-swaps the live model after the alias has been promoted.
7. **Open Grafana** (top-bar link) — show the four `fraudshield_*` dashboards (API Performance, Model Behavior, Drift & Retraining, System Health) reflecting the traffic the demo just generated.
8. **Open MLflow** (top-bar link) — show the registered `fraud-detector` model, the production alias, archived versions.

The narrative arc: a transaction goes in (Predict), the system logs it (Logs), drift detection notices distribution shift (Monitoring), retraining kicks in and beats the champion (Experiments), and the whole loop is observable in real time (Grafana). Closed-loop MLOps in 5 minutes.

### 15. How does the CI/CD pipeline work? (Phase 9)

GitHub Actions ships two workflows.

* **`ci.yml`** runs on every push to `main`/`develop` and every PR. Four parallel jobs: `backend-lint-test` (ruff lint + ruff format check + pytest with `--cov-fail-under=65`; currently 76%), `frontend-lint-build` (`npm ci` → `npm run lint` → `npm run build`), `docker-build` (Buildx for both Dockerfiles, no push, just verify they still build), and `precommit` (runs every hook against the full tree). Concurrency is keyed by ref so PR fixups cancel the previous run.
* **`cd.yml`** runs on push to `main` and `workflow_dispatch`. It always *builds* both images via Buildx — that catches Dockerfile regressions even when there's no deploy target — and only *pushes* to `ghcr.io/<owner>/<repo>-{backend,frontend}` when `secrets.GHCR_TOKEN` is set. Render + Vercel deploy hooks fire conditionally too. The net effect: CD is safe to merge today (it skips push when secrets are absent), and Phase 10 turns it on by just adding the three repo secrets.

### 16. Why do the tests not require live infrastructure?

Production reliability of a test suite is measured by how fast it runs and how predictably it passes. Live infrastructure breaks both: a flaky Postgres or an offline MLflow turns CI green/red on factors that have nothing to do with the code under test. So every test path uses one of three substitutes:

* **In-memory SQLite via `aiosqlite`** — same SQLAlchemy 2.0 async API as production Postgres; the `JSON()/JSONB` and `GUID()/UUID` columns use platform-aware variants in the ORM so the model code runs unchanged.
* **`DummyFraudModel`** — a deterministic stand-in that satisfies the `predict_proba` contract; the dependency-injection layer hands it to the routers via `app.dependency_overrides`, so the routers never know the difference.
* **Monkey-patched Prefect tasks** — the workflow tests stub each task at the module boundary, so flows execute end-to-end without a Prefect server, MLflow tracking, or training.

That's why the CI runtime is under 90 seconds end-to-end and why we can run the full suite in PR review without provisioning anything.

### 17. Why Docker Compose for local production simulation?

Compose gives us a one-command (`make docker-up`) reproduction of the full multi-service shape — Postgres, MLflow, FastAPI, Prefect, Prometheus, Grafana, Next.js — with the same networking, healthchecks, named volumes, and non-root containers production would have. It's not Kubernetes, but it's *production-equivalent in topology*: every service talks to every other service the same way they would in prod. That means a bug that depends on cross-service interaction (a Prometheus scrape failing because the API's `/metrics` is at a different path; a Grafana datasource that doesn't resolve `prometheus:9090`) shows up locally, not in production. And it's cheap to throw away: `make docker-down` and you're at a clean slate.

### 18. How would you move this to Kubernetes?

The compose file already does 80% of the structural work — each service is independently containerised, talks over a well-known DNS name, has a healthcheck, and stores state in a named volume. The K8s migration becomes:

1. **One Deployment per stateless service** (api, frontend, prefect-flows worker) with the existing healthcheck repurposed as `readinessProbe` / `livenessProbe`.
2. **StatefulSet for Postgres** plus a PersistentVolumeClaim that mirrors the `postgres_data` volume.
3. **Helm chart or Kustomize overlay** for the existing env-var configuration. The `.env.example` keys become a `ConfigMap`, and the `*_PASSWORD` / `API_KEY` entries become a `Secret`.
4. **Horizontal Pod Autoscaler** on the api Deployment keyed off the `fraudshield_requests_in_progress` gauge — exactly the kind of custom metric Phase 7 was designed to surface.
5. **kube-prometheus-stack** swaps in for the bundled Prometheus + Grafana, with the same scrape config and dashboard JSON we ship today.

Nothing in the app changes. That's the design goal: the Phase 9 Compose stack is the development-time stencil for a Phase 11 Kubernetes deployment.

### 19. How do you explain quality gates in interviews?

Five layers, each enforcing a single, measurable property:

1. **Pre-commit** catches the boring stuff before code leaves the developer's machine (trailing whitespace, large files, accidentally committed private keys).
2. **Ruff** (lint + format) enforces a single canonical Python style; we pinned the exact version to the pre-commit hook so "works on my machine" never diverges from CI.
3. **Pytest with `--cov-fail-under=65`** is the correctness gate. The floor is conservative enough that adding 50 lines of code without a test won't tank the build, but high enough that we can't gut the suite and notice nothing.
4. **Ruff format check** in CI runs after the format pass to catch "I forgot to run `make format` before pushing" — a one-liner failure with the diff right there.
5. **Docker build verification** in CI catches the surprisingly common case where `requirements.txt` works locally but breaks in the slim image because of a missing system library.

Each gate is *local-runnable* (`make lint`, `make test-backend`, `make docker-build`) so failures are debuggable without burning CI cycles. That's what makes the pipeline feel fast even when it has 4 jobs.

### 20. What would you do differently with more time?

Coming in Phase 10.

See [FRAUDSHIELD_BLUEPRINT.md](../FRAUDSHIELD_BLUEPRINT.md) §10 for the short-form answers.
