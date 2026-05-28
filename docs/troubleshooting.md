# Troubleshooting

Common failures encountered while running FraudShield locally, plus the
fix that has worked in practice. Issues are ordered by frequency.

## 1. Docker Compose can't find the file

> `no configuration file provided: not found`

You ran `docker compose ...` from the project root without telling it
where the compose file lives. The file is inside `infra/`, not the
repo root.

**Fix:** always use the Makefile (which already passes the flag), or
spell it out:

```bash
docker compose -f infra/docker-compose.yml --env-file .env up -d
# or simply
make docker-up
```

## 2. Port already in use

> `Bind for 0.0.0.0:8001 failed: port is already allocated`

Another process is using 8001 (most often a previous FraudShield run
that didn't clean up). The blueprint deliberately maps the API host
port to 8001 instead of 8000 because some dev machines have a non-MLOps
service on 8000.

**Fix:**

```bash
make docker-down                                 # graceful first
docker ps                                        # confirm nothing on 8001
# if still occupied, find the holder:
docker compose -f infra/docker-compose.yml --env-file .env down --remove-orphans
# Windows: netstat -ano | findstr 8001
# macOS / Linux: lsof -iTCP:8001 -sTCP:LISTEN
```

If you genuinely need to remap, edit `infra/docker-compose.yml`'s
`api.ports` block and update `NEXT_PUBLIC_API_URL` to match.

## 3. PostgreSQL never goes healthy

> `dependency failed to start: container fraudshield-postgres is unhealthy`

The healthcheck is `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`.
If `.env` is missing those variables it never passes.

**Fix:**

```bash
cp .env.example .env                              # copy fresh defaults
docker compose -f infra/docker-compose.yml --env-file .env logs postgres | tail -30
docker volume rm fraudshield-mlops_postgres_data  # nuke a corrupted volume
make docker-up
```

## 4. MLflow can't connect to PostgreSQL

> `psycopg2.OperationalError: connection to server at "postgres" ... failed`

MLflow started before Postgres finished its first-run init scripts.

**Fix:**

```bash
docker compose -f infra/docker-compose.yml --env-file .env restart mlflow
# watch the logs settle:
docker compose -f infra/docker-compose.yml --env-file .env logs -f mlflow
```

The Compose `depends_on: postgres condition: service_healthy` should
prevent this; if it recurs, your healthcheck `start_period` may be too
short for slow disks.

## 5. /ready returns 503 — model not loaded

`load_model_safely()` couldn't reach MLflow *or* the model isn't
registered yet. By default the API falls back to a `DummyFraudModel` so
this only happens in production-equivalent mode.

**Fix (local):**

```bash
make train-mlflow                                 # register the model
make promote-model VERSION=1                      # alias it production
make trigger-reload API_KEY=change-me             # hot-reload the API
curl -s http://localhost:8001/ready | python -m json.tool
```

If you're intentionally running without MLflow, set
`ALLOW_DUMMY_MODEL=true` in `.env` and restart the API.

## 6. Why am I seeing the dummy model in production?

`ALLOW_DUMMY_MODEL=true` is the default in `.env.example` so local dev
just works. **In production it MUST be `false`**, otherwise a registry
outage silently downgrades you to the deterministic stub model.

**Fix:** set `ALLOW_DUMMY_MODEL=false` in `.env.production` (template at
`.env.production.example`).

## 7. Alembic migration errors

> `alembic.util.exc.CommandError: Can't locate revision identified by '...'`

Most often: your local DB volume was created against an older revision
graph and Alembic's `alembic_version` table now disagrees with the
migration files.

**Fix for a throwaway dev environment:**

```bash
make docker-down
docker volume rm fraudshield-mlops_postgres_data
make docker-up
make db-upgrade                                   # apply Phase 4 → 5 → 6
```

In production you must reconcile properly (`alembic history`,
`alembic stamp <revision>`, hand-rolled migration). Never `volume rm`
prod.

## 8. Frontend can't reach the backend

> `Failed to fetch http://localhost:8001/v1/predict — Network error`

Two common causes:

* The frontend was built before `NEXT_PUBLIC_API_URL` was set —
  `NEXT_PUBLIC_*` vars are baked into the bundle at build time, so a
  later `docker compose restart frontend` does nothing.
* The API container is healthy but the dashboard is hitting the wrong
  port (8000 instead of 8001 from the host).

**Fix:**

```bash
make docker-build                                 # rebuilds with current env
NEXT_PUBLIC_API_URL=http://localhost:8001 make docker-up
```

For `npm run dev` (local), set `frontend/.env.local`:

```bash
echo "NEXT_PUBLIC_API_URL=http://localhost:8001" > frontend/.env.local
```

## 9. CORS error in the browser console

> `Access to fetch at 'http://localhost:8001/...' from origin
> 'http://localhost:3000' has been blocked by CORS policy`

The API allows `settings.FRONTEND_URL` and `http://localhost:3000`. If
you're running the dashboard on a different origin (e.g. `127.0.0.1`,
or behind a tunnel), add it to `FRONTEND_URL` in `.env` and restart the
API:

```bash
echo "FRONTEND_URL=http://127.0.0.1:3000" >> .env
make docker-restart
```

## 10. Prometheus target is DOWN

Open http://localhost:9090/targets — `fraudshield-api` is red.

Most often the API container isn't healthy yet, or the
`prometheus.yml` scrape target uses the wrong DNS name.

**Fix:**

```bash
curl -fsS http://localhost:8001/health            # confirm API is up
docker compose -f infra/docker-compose.yml --env-file .env logs prometheus | tail -30
# config inside the container resolves "api" via docker-compose DNS;
# from a host shell you would use "localhost", not "api".
```

## 11. Grafana dashboards not loading

> Grafana opens but the **FraudShield** folder is empty.

The provisioning bind-mount didn't pick up your changes, or the JSON
sits in the wrong subdirectory.

**Fix:**

```bash
ls infra/grafana/provisioning/dashboards/         # 4 JSON files expected
docker compose -f infra/docker-compose.yml --env-file .env restart grafana
docker compose -f infra/docker-compose.yml --env-file .env logs grafana | grep -i provision
```

Common gotcha: editing a dashboard inside Grafana's UI doesn't write
back to the file. Save your changes by exporting JSON and replacing the
checked-in file.

## 12. Prefect server not reachable

> `httpcore.ConnectError: All connection attempts failed`

Prefect server is slow to boot (~20–30 s on a cold start). The healthcheck
allows for that with `start_period: 20s`. If it stays unhealthy:

**Fix:**

```bash
docker compose -f infra/docker-compose.yml --env-file .env logs prefect | tail -50
docker compose -f infra/docker-compose.yml --env-file .env restart prefect
# Need to actually schedule the flows? They live behind a profile:
docker compose -f infra/docker-compose.yml --profile flows up -d prefect-flows
```

## 13. Evidently report generation fails

> `DriftError: Evidently failed to compute drift: ...`

Usually a column shape mismatch — the reference DataFrame has columns
the current DataFrame doesn't.

**Fix:**

```bash
make seed-logs                                    # seed a baseline first
make seed-drift                                   # then the drifted window
make drift-check                                  # local CLI run
# inspect the rendered report:
ls backend/reports/drift/
```

If the failure persists, regenerate the reference parquet so it matches
the current feature schema:

```bash
rm backend/data/reference/reference.parquet
make generate-data
```

## 14. Missing reference dataset

> `DriftDataError: Reference dataset not found at ...`

The reference parquet hasn't been generated yet (or was deleted by
`make clean`).

**Fix:** `make generate-data` writes train/test/reference all at once.

## 15. `npm run build` errors

> `Type error: ...`

The most common Phase 8 → 10 trap is `recharts` typed-tooltip
formatters. We use the pattern
`(v) => typeof v === "number" ? ... : String(v)` because `v` is
`ValueType | undefined`.

**Fix:**

```bash
cd frontend
rm -rf .next node_modules                         # nuke the cache
npm ci
npm run lint
npm run build
```

If the error mentions `next/core-web-vitals`, confirm
`frontend/.eslintrc.json` exists with that exact `extends` value.

## 16. Python import path errors

> `ModuleNotFoundError: No module named 'src'`

You ran a script from the wrong directory. Every Python entrypoint
assumes the working directory is `backend/`, which is why the Makefile
prefixes them with `cd backend && ...`.

**Fix:**

```bash
cd backend
python -m pytest tests/ -q
python scripts/run_smoke_test.py --base-url http://localhost:8001
# or from the project root:
PYTHONPATH=backend python backend/scripts/run_smoke_test.py
```

---

Still stuck? Open a bug report (the template lives at
[`.github/ISSUE_TEMPLATE/bug_report.md`](../.github/ISSUE_TEMPLATE/bug_report.md))
with the smoke-test output, the relevant container logs, and your OS /
Docker version.
