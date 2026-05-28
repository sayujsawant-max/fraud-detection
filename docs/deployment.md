# Deployment

> **Status:** Placeholder — full deployment guide ships in **Phase 9**.

## Local (Phase 0)

```bash
cp .env.example .env
make docker-up
```

## Cloud Targets (Phase 9)

- **Frontend** → Vercel (free tier)
- **Backend API** → Render (free tier, spins down)
- **PostgreSQL** → Render Managed Postgres
- **MLflow** → Render Web Service + persistent disk
- **Prefect** → Prefect Cloud (free tier)
- **Grafana** → Grafana Cloud (free tier) or Railway

Detailed step-by-step deployment instructions are documented in Phase 9.
