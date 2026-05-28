# Architecture diagram (Mermaid)

This file is the canonical source for the FraudShield architecture
diagram. Render it inline on GitHub, or export to PNG and drop the result
at `docs/assets/screenshots/architecture.png` for the README hero.

## Render

```mermaid
flowchart TB
    subgraph User["👤 User"]
        BR["Browser"]
    end

    subgraph Frontend["🖥️ Frontend (port 3000)"]
        NX["Next.js 14 Dashboard<br/>Overview · Predict · Monitoring<br/>Experiments · Logs · Settings"]
    end

    subgraph Backend["⚙️ Backend (host 8001 → container 8000)"]
        API["FastAPI<br/>/v1/predict · /v1/logs<br/>/v1/monitoring/* · /v1/retraining/*<br/>/v1/admin/* · /metrics"]
        MID["PrometheusMiddleware<br/>fraudshield_* metrics"]
    end

    subgraph Data["💾 Data + Storage"]
        PG[("PostgreSQL 16<br/>prediction_logs · drift_reports<br/>retraining_runs")]
        REF[("Reference parquet<br/>backend/data/reference/")]
    end

    subgraph ML["🤖 ML Tracking + Registry"]
        MLF["MLflow Server<br/>port 5000"]
        REG["Model Registry<br/>fraud-detector<br/>aliases: production, champion"]
    end

    subgraph Drift["📊 Drift Detection"]
        EV["Evidently AI<br/>DataDriftPreset"]
        REPS[("Drift artifacts<br/>backend/reports/drift/*.html")]
    end

    subgraph Orch["🔄 Orchestration (port 4200)"]
        PRE["Prefect 3 Server"]
        MFLOW["monitoring_flow<br/>every 6h cron"]
        RFLOW["retraining_flow<br/>weekly cron"]
    end

    subgraph Obs["📈 Observability"]
        PROM["Prometheus<br/>port 9090<br/>15s scrape"]
        GRAF["Grafana<br/>port 3001<br/>4 dashboards"]
    end

    BR --> NX
    NX -->|"REST"| API
    API --> MID
    MID -->|"metrics"| PROM
    API -->|"async write"| PG
    API -->|"load model"| MLF
    MLF <--> REG

    EV --> REF
    EV --> PG
    EV --> REPS
    API --> EV

    MFLOW --> EV
    MFLOW -->|"drift_detected=True"| RFLOW
    RFLOW -->|"register + promote"| REG
    RFLOW -->|"audit row"| PG
    RFLOW -->|"POST /v1/admin/reload-model"| API
    PRE --> MFLOW
    PRE --> RFLOW

    PROM --> GRAF
```

## Quick-export to PNG

Mermaid Live (no install required):

1. Open <https://mermaid.live>
2. Paste the diagram source (from the code fence above)
3. Use the **Actions → PNG** button
4. Save as `docs/assets/screenshots/architecture.png`

Or from the CLI with `@mermaid-js/mermaid-cli`:

```bash
npx -y @mermaid-js/mermaid-cli -i docs/assets/architecture-diagram.md \
  -o docs/assets/screenshots/architecture.png -b transparent -w 1600
```
