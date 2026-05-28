# Deployment

> **Status (Phase 9):** local Docker Compose is the production-equivalent
> environment. Public deployment + CD against real cloud providers lands
> in **Phase 10**. This document captures the deployment checklist, the
> CI/CD shape, and the secrets we'll need to wire up next.

## 1. Local production-like run

The full stack is a single command. There is no separate "prod" compose
file in Phase 9 — every service is configured to match the production
shape (non-root containers, healthchecks, named volumes, restart policy)
with the only concession being that `api` and `prefect-flows` bind-mount
the live source for hot reload during demos.

```bash
cp .env.example .env
make docker-up               # starts: postgres, mlflow, api, prefect,
                             # prometheus, grafana, frontend
make docker-ps               # watch healthchecks turn UP
make smoke-full              # exercise every backend endpoint
make load-test               # send 100 demo predictions
```

Once the smoke test is green, open:

| Service     | URL                         | Notes                                   |
| ----------- | --------------------------- | --------------------------------------- |
| Dashboard   | http://localhost:3000       | Next.js                                 |
| API         | http://localhost:8001       | Host port 8001 → container port 8000    |
| API docs    | http://localhost:8001/docs  | Swagger                                 |
| MLflow      | http://localhost:5000       | Experiments + registry                  |
| Prefect     | http://localhost:4200       | Flow runs                               |
| Prometheus  | http://localhost:9090       | Scrape targets at `/targets`            |
| Grafana     | http://localhost:3001       | admin / admin · FraudShield folder      |

## 2. Required environment variables

`.env.example` is the source of truth — copy it to `.env` and fill in
real values. The keys that matter for **production** deployment:

| Key                          | Why                                                  |
| ---------------------------- | ---------------------------------------------------- |
| `POSTGRES_USER`/`PASSWORD`/`DB` | Postgres credentials                                |
| `DATABASE_URL`               | Async SQLAlchemy URL (auto-translated for sync use) |
| `MLFLOW_TRACKING_URI`        | URL the API + flows read from                       |
| `MLFLOW_MODEL_NAME`          | Registered model name (`fraud-detector`)            |
| `API_KEY`                    | Admin endpoints; **change for prod**                |
| `ALLOW_DUMMY_MODEL`          | Must be `false` in prod                             |
| `MODEL_PROMOTION_MIN_DELTA`  | Retraining gate (default 0.01)                      |
| `API_BASE_URL`               | URL the retraining flow uses for `/v1/admin/reload-model` |
| `PREFECT_API_URL`            | Prefect Cloud or self-hosted server                 |
| `PREFECT_API_KEY`            | Required for Prefect Cloud                          |
| `NEXT_PUBLIC_API_URL`        | Inlined into the Next.js bundle at build time       |
| `DRIFT_THRESHOLD`            | 0.30 default                                        |

Anything containing `PASSWORD`/`KEY`/`SECRET` lives in `.env` (which is
git-ignored). `.env.example` ships safe placeholders only.

## 3. CI — `.github/workflows/ci.yml`

Triggers: `push` to `main`/`develop`, every PR against those branches,
and manual `workflow_dispatch`. Four parallel jobs:

| Job                  | What it does                                         | Required infra |
| -------------------- | ---------------------------------------------------- | -------------- |
| `backend-lint-test`  | ruff lint + ruff format check + pytest with `--cov-fail-under=65` (we currently sit at 76%) | None |
| `frontend-lint-build`| `npm ci` → `npm run lint` → `npm run build`          | None           |
| `docker-build`       | Buildx for backend + frontend Dockerfiles (no push)  | None           |
| `precommit`          | `pre-commit run --all-files`                         | None           |

The CI **never** requires a live PostgreSQL, MLflow, Prefect, Prometheus,
Grafana, or any secret. Every test path goes through a dummy predictor,
in-memory SQLite, or monkey-patched task — see the [Interview Guide](./interview-guide.md)
for the "why".

## 4. CD — `.github/workflows/cd.yml`

Triggers: `push` to `main`, plus manual `workflow_dispatch`.

The job is built to be **safe to land before secrets exist**:

1. **Always builds** both backend + frontend images via Buildx (catches
   Dockerfile drift even when there's no deploy target yet).
2. **Pushes** to `ghcr.io/<owner>/<repo>-{backend,frontend}` only when
   `secrets.GHCR_TOKEN` is configured. Without the secret, the build
   stage exits 0 and the deploy stage is skipped.
3. **Deploy hooks** (Render + Vercel) only fire when their respective
   `secrets.RENDER_DEPLOY_HOOK` / `secrets.VERCEL_DEPLOY_HOOK` are
   present. Otherwise the job logs "no deploy hooks configured" and
   exits 0.

This means Phase 9 CD can be merged today without breaking — and Phase
10 turns it on by adding three repo secrets.

## 5. Phase 10 deployment checklist

When you're ready to ship publicly, the work breaks down as:

- [ ] Pick hosting targets (sketched below).
- [ ] Create the database first; capture its connection URL.
- [ ] Create the MLflow tracking server; capture its URL.
- [ ] Run `make generate-data && make train-mlflow && make promote-model VERSION=1` against the live MLflow.
- [ ] Configure `.env` on each compute host with real `API_KEY`, `MLFLOW_TRACKING_URI`, `DATABASE_URL`, `NEXT_PUBLIC_API_URL`.
- [ ] Add GitHub repo secrets: `GHCR_TOKEN`, `RENDER_DEPLOY_HOOK`, `VERCEL_DEPLOY_HOOK`.
- [ ] Push to `main` — CD builds + pushes images + triggers deploy hooks.
- [ ] Wire Prometheus + Grafana to the real API (single scrape target swap).
- [ ] Smoke test against the public URL: `make smoke-full SMOKE_BASE_URL=https://api.example.com`.

### Suggested cloud targets

| Layer         | Suggested provider                                  |
| ------------- | --------------------------------------------------- |
| Frontend      | Vercel (free tier)                                  |
| Backend API   | Render (free tier; cold start acceptable for demo)  |
| PostgreSQL    | Render Managed Postgres / Neon                      |
| MLflow        | Render Web Service + persistent disk                |
| Prefect       | Prefect Cloud (free tier)                           |
| Prometheus    | Grafana Cloud (free tier) or Fly.io                 |
| Grafana       | Grafana Cloud                                       |

## 6. Local Phase 6 — Prefect operations

The bare `make docker-up` brings up the Prefect *server* (UI on
http://localhost:4200) but not the scheduled worker. Two ways to run
flows locally:

### Option A — Deploy + serve flows manually (recommended for local dev)

```bash
make deploy-prefect-flows
```

Blocks in `prefect serve(...)`. Stop with Ctrl+C. The Prefect UI shows
two deployments — `fraud-monitoring-every-6h` and `fraud-retraining-weekly`.

### Option B — Run the bundled `prefect-flows` container

```bash
docker compose -f infra/docker-compose.yml --profile flows up -d prefect-flows
```

Same effect, just inside the Docker stack. Tail logs with
`docker compose logs -f prefect-flows`.

### One-shot manual runs (no schedule)

```bash
make run-monitoring-flow         # run the monitoring flow once
make run-retraining-flow         # run the retraining flow once
```

### Admin endpoints

```bash
make trigger-retrain API_KEY=change-me      # POST /v1/admin/retrain
make trigger-monitoring API_KEY=change-me   # POST /v1/admin/monitoring/run
make trigger-reload API_KEY=change-me       # POST /v1/admin/reload-model
make retraining-runs                        # GET  /v1/retraining/runs
```
