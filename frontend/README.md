# FraudShield Frontend

Next.js 14 (App Router) dashboard for FraudShield MLOps.

## Phase 0

Phase 0 ships only a placeholder landing page that confirms the build and Docker pipeline work. The full dashboard — prediction form, KPI cards, drift report viewer, MLflow experiments table, prediction log browser, admin actions — is built in **Phase 7**.

## Local development

```bash
npm install
npm run dev          # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`) to point at your running FastAPI backend.

## Build

```bash
npm run build
npm run start
```

## Docker

The frontend is built and run by the root `docker compose` stack — see `infra/docker-compose.yml`.
