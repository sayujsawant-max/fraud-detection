# Deployment

> **Status (Phase 10):** Phases 0–10 are complete. The project is
> portfolio-ready. This document describes seven deployment options
> (A–G) for the FraudShield MLOps stack. Local Docker Compose is the
> recommended demo path; the public-cloud options exist for when you
> want a live link in your portfolio.

## Deployment options at a glance

| Option | Layer | Provider | Cost (free tier) | Recommended? |
| --- | --- | --- | --- | --- |
| **A** | Full stack | Local Docker Compose | $0 | ✅ Demo + interview |
| **B** | Frontend | Vercel | $0 | ✅ Public demo |
| **C** | Backend API | Render Web Service | $0 (with cold starts) | ✅ Public demo |
| **D** | PostgreSQL | Render / Neon | $0 (~256 MB) | ✅ Public demo |
| **E** | MLflow | Render Web Service + persistent disk | $0 / month w/ disk caveat | ⚠️ Local screenshot preferred |
| **F** | Prefect | Prefect Cloud | $0 | ✅ Public demo |
| **G** | Observability | Grafana Cloud / Prometheus | $0 | ⚠️ Local screenshot preferred |

Quick rule of thumb: **A + B + C + D + F = portfolio-ready public
demo**. E and G are usually better as local screenshots so you keep
costs predictable and the demo deterministic.

---

## Option A — Local Docker Compose (recommended)

The Phase 0–9 default. One command brings up the entire 7-service stack
with healthchecks, named volumes, and a non-root runtime.

```bash
# 1. Clone + configure
git clone https://github.com/<your-username>/fraud-detection.git
cd fraud-detection
cp .env.example .env

# 2. Bring up the stack
make docker-up
make docker-ps                       # wait until everything is "healthy"

# 3. Seed the system with data
make generate-data                   # train/test/reference parquet
make train-mlflow                    # 3 model families, register champion
make promote-model VERSION=1         # flip the production alias
make db-upgrade                      # alembic migrate (3 tables)
make seed-logs                       # 100 baseline predictions
make load-test                       # 100 demo predictions

# 4. Verify everything works
make smoke-full
```

Open:

| URL | Service |
| --- | --- |
| http://localhost:3000             | Dashboard (Next.js) |
| http://localhost:8001/docs        | FastAPI Swagger |
| http://localhost:5000             | MLflow |
| http://localhost:4200             | Prefect |
| http://localhost:9090             | Prometheus |
| http://localhost:3001             | Grafana (admin / admin) |

Stop the stack with `make docker-down`.

---

## Option B — Frontend on Vercel

Vercel's free tier is the right home for the Next.js dashboard. Build
takes ~90 s; the public URL is on the next push.

### Prerequisites

* GitHub repo is public (or Vercel is connected to your GitHub account).
* The backend is reachable at a public URL (Option C below).

### Steps

1. **Import the project** at <https://vercel.com/new>.
2. **Root directory:** `frontend`. Vercel detects Next.js automatically.
3. **Build command:** `npm run build` (default — leave as-is).
4. **Output directory:** `.next` (default).
5. **Environment variables:**
   * `NEXT_PUBLIC_API_URL` = your public Render API URL from Option C
     (e.g. `https://fraudshield-api.onrender.com`)
6. **Deploy.** First build takes ~90 s.

Subsequent deploys are automatic on every push to `main`. Preview
deploys land on every PR.

### Wire up CI

The `cd.yml` workflow can fire a Vercel deploy hook on push to `main`
once you add the secret:

```bash
# Vercel → Project Settings → Git → Deploy Hooks → Create Hook
# Copy the URL into GitHub Settings → Secrets → Actions → New repo secret
VERCEL_DEPLOY_HOOK = <hook URL>
```

---

## Option C — Backend on Render

The Render free Web Service tier cold-starts after 15 minutes of
inactivity (~30 s wake-up). Acceptable for a demo; not acceptable for a
real product.

### Steps

1. **New → Web Service → Build and deploy from a Git repository.**
2. **Root directory:** `backend`.
3. **Runtime:** Python 3.11.
4. **Build command:**
   ```bash
   pip install --upgrade pip && pip install -r requirements.txt
   ```
5. **Start command:**
   ```bash
   uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
   ```
6. **Health check path:** `/health`.
7. **Environment variables** (paste from `.env.production.example`):
   * `DATABASE_URL` — set to the Render Postgres internal URL from
     Option D (don't expose Postgres publicly).
   * `MLFLOW_TRACKING_URI` — Option E URL or `http://localhost:5000`
     if you're not deploying MLflow.
   * `API_KEY` — random 32+ char secret. **Never** the dev default.
   * `ALLOW_DUMMY_MODEL` — **`false`** in production.
   * `DRIFT_THRESHOLD` — `0.30` (or your value).
   * `FRONTEND_URL` — your Vercel URL (for CORS).
   * `API_BASE_URL` — your Render API URL (the retraining flow uses
     this for `/v1/admin/reload-model`).
   * `PREFECT_API_URL`, `PREFECT_API_KEY` — from Option F.
8. **Deploy.**

### Post-deploy

```bash
# Run migrations once (via Render shell or one-off job):
alembic upgrade head

# Smoke-test:
python backend/scripts/run_smoke_test.py --base-url https://<your-app>.onrender.com
```

---

## Option D — PostgreSQL on Render

Render Managed Postgres free tier provides ~256 MB storage. Neon's free
tier (~3 GB) is also excellent and uses the same connection string.

### Render PostgreSQL steps

1. **New → PostgreSQL.**
2. Pick a name, region (same as the API), free plan.
3. Wait ~2 min for provisioning.
4. Copy the **Internal Database URL** (starts with
   `postgres://...internal:5432/...`). The internal URL only works
   from inside Render, which is what you want — Postgres should never
   be public.
5. Paste that URL as `DATABASE_URL` in Option C's environment.
6. Run migrations from the API service shell:
   ```bash
   alembic upgrade head
   ```

### Neon alternative

1. Create a project at <https://neon.tech>.
2. Copy the connection string (`postgresql://...pooler.neon.tech/...`).
3. Same `DATABASE_URL` env var on Render.

---

## Option E — MLflow deployment

Two paths:

### E.1 — Keep MLflow local for the portfolio (recommended)

The dashboard's Experiments page links to the local MLflow UI. For
public demos, take a screenshot of the experiment list with three runs
and the champion alias, drop it at
`docs/assets/screenshots/mlflow-runs.png`, and link from the README.

The Render-deployed API can still resolve `MLFLOW_TRACKING_URI` to a
non-existent host as long as `ALLOW_DUMMY_MODEL=false` AND the model
has been baked into the Docker image during the build (out of scope
for the free tier).

### E.2 — Deploy MLflow as a Render Web Service

For when you want the live tracking UI public.

1. Create a new Render Web Service.
2. **Runtime:** Docker.
3. Point the Dockerfile at `infra/mlflow/Dockerfile` (build context:
   `infra/mlflow/`).
4. **Persistent disk:** mount at `/mlflow/artifacts` (1 GB tier).
5. **Start command:**
   ```bash
   mlflow server \
     --host 0.0.0.0 \
     --port $PORT \
     --backend-store-uri $DATABASE_URL \
     --default-artifact-root /mlflow/artifacts
   ```
6. **Environment:**
   * `DATABASE_URL` — same Render Postgres URL as the API.

> **Security note:** Public MLflow exposes the model registry and run
> artifacts. Either put it behind Render's basic auth, or front it with
> a Cloudflare Tunnel + Access policy. The Phase 10 portfolio path is
> usually to keep it local and screenshot it.

---

## Option F — Prefect Cloud

Prefect Cloud's free tier covers one workspace and unlimited
deployments — plenty for FraudShield's two flows.

### Steps

1. Sign up at <https://app.prefect.cloud>.
2. Create a workspace (free tier).
3. Generate an API key: **Settings → API Keys → Create**.
4. Copy the workspace API URL (Settings → API URL) and the API key.
5. Paste into Render (Option C environment):
   * `PREFECT_API_URL` = workspace URL
     (e.g. `https://api.prefect.cloud/api/accounts/<id>/workspaces/<id>`)
   * `PREFECT_API_KEY` = the key
6. From your local machine, deploy the flows:
   ```bash
   make deploy-prefect-flows
   ```

The flows now show up in the Prefect Cloud UI on cron, even when your
laptop is closed.

### Skip Prefect Cloud for a local-only demo

The Phase 6 deployment script works against the bundled Prefect server
inside the Compose stack — no cloud account needed.

---

## Option G — Grafana / Prometheus

### G.1 — Local screenshots (recommended)

Run `make load-test` and screenshot the four FraudShield dashboards at
http://localhost:3001 under the **FraudShield** folder. Drop into
`docs/assets/screenshots/`:

* `grafana-dashboard.png` — Model Behavior
* (optional) `grafana-system-health.png`, etc.

### G.2 — Grafana Cloud free tier

1. Create a Grafana Cloud account.
2. Get the Prometheus remote-write URL + API key.
3. Add a remote-write block to `infra/prometheus/prometheus.yml`:
   ```yaml
   remote_write:
     - url: https://prometheus-prod-<region>.grafana.net/api/prom/push
       basic_auth:
         username: <prom-instance-id>
         password: <api-key>
   ```
4. Import the four `infra/grafana/provisioning/dashboards/*.json` files
   into Grafana Cloud via **Dashboards → Import JSON**.

> Costs may apply above the free tier's metric retention limits. The
> free tier is enough for a demo.

---

## Production environment checklist

Before you go public, work through this list:

* [ ] `.env.production` has no leftover dev defaults (`change-me`,
      `fraudshield_password`, …).
* [ ] `ALLOW_DUMMY_MODEL=false` everywhere.
* [ ] `API_KEY` is a random 32+ char secret you've stored in a password
      manager.
* [ ] `DATABASE_URL` uses the internal database hostname, not the public
      one.
* [ ] `FRONTEND_URL` matches the Vercel deployment URL exactly (CORS).
* [ ] `NEXT_PUBLIC_API_URL` on Vercel matches the Render API URL exactly
      (it's baked into the JS bundle at build time).
* [ ] `MLFLOW_TRACKING_URI` is reachable from the API at runtime.
* [ ] First Alembic migration ran successfully against the public DB.
* [ ] First MLflow model is registered + aliased `production`.
* [ ] CORS headers are present on `OPTIONS` preflight.
* [ ] Prometheus scrape targets are UP at the public API.
* [ ] Smoke test against the public URL is green:
      `python backend/scripts/run_smoke_test.py --base-url https://<api-url>`
* [ ] GitHub Actions CI is green on `main`.
* [ ] `.github/workflows/cd.yml` has the `GHCR_TOKEN`,
      `RENDER_DEPLOY_HOOK`, and (optionally) `VERCEL_DEPLOY_HOOK`
      secrets configured.

## Deployment troubleshooting

* **Render API returns 503 immediately after deploy.** Cold start. Hit
  `/health` once to wake the dyno; subsequent requests are fast.
* **CORS error from Vercel → Render.** `FRONTEND_URL` on the API must
  exactly match the Vercel URL (no trailing slash). Restart the API.
* **MLflow model not found in production.** Run
  `make train-mlflow && make promote-model VERSION=1` against the
  public MLflow before flipping `ALLOW_DUMMY_MODEL` to false.
* **Prefect deployments never run.** The Prefect Cloud workspace needs
  a worker; for `flow.serve()` the worker is embedded — make sure the
  process is still running.
* **Postgres "too many connections."** Lower `DB_POOL_SIZE` /
  `DB_MAX_OVERFLOW` in the API env. Free-tier Postgres caps connections
  around 20.

The full troubleshooting catalogue lives in
[`docs/troubleshooting.md`](troubleshooting.md).

## Cost estimate

Free-tier-only ("interview demo"):

| Layer | Provider | Monthly cost |
| --- | --- | --- |
| Frontend | Vercel free | $0 |
| Backend API | Render Web Service free | $0 (with cold starts) |
| Database | Render Postgres free | $0 (256 MB) |
| Tracking | Local screenshot | $0 |
| Orchestration | Prefect Cloud free | $0 |
| Observability | Local screenshot | $0 |
| **Total** | | **$0/month** |

Production-grade ("real product"):

| Layer | Provider | Monthly cost |
| --- | --- | --- |
| Backend API | Render Standard ($7) or Fly Performance ($5) | $5–7 |
| Database | Neon Pro or Render Standard | $19 |
| MLflow | Render Standard + persistent disk | $7 + $1/GB |
| Prefect | Prefect Cloud paid | $0 (free under 20 k task runs/month) |
| Grafana Cloud Pro | optional | $0–8 |
| **Total** | | **~$32–42/month** |

## Security notes

* **Admin API key.** Treat it like a password. Rotate via Render env-var
  update + `make trigger-reload` (no code change required).
* **MLflow public exposure.** If you must expose MLflow publicly, put it
  behind Cloudflare Access or Render basic auth. Otherwise anyone can
  download your model artifacts.
* **Prefect Cloud API key.** Stays inside the API service. Never inline
  it into the Next.js bundle.
* **Vercel preview deploys.** Use a *different* API URL for previews
  (a staging Render service) so PRs can't accidentally write to
  production data.
* **GitHub repo secrets.** `GHCR_TOKEN` needs `write:packages` scope.
  Deploy hooks need no scope (URL is the secret). Document rotations in
  a runbook.

See `docs/troubleshooting.md` for fix recipes and the
[Phase 9 Interview Guide §19](interview-guide.md) for the full
security-posture answer.
