import type { ReactNode } from "react";

type ServiceCard = {
  name: string;
  role: string;
  port: string;
};

const services: ServiceCard[] = [
  { name: "FastAPI", role: "Prediction API", port: ":8000" },
  { name: "MLflow", role: "Experiments + Registry", port: ":5000" },
  { name: "Evidently AI", role: "Drift Detection", port: "—" },
  { name: "Prefect", role: "Workflow Orchestration", port: ":4200" },
  { name: "Prometheus", role: "Metrics", port: ":9090" },
  { name: "Grafana", role: "Dashboards", port: ":3001" },
  { name: "PostgreSQL", role: "Prediction Logs", port: ":5432" },
];

export default function HomePage(): ReactNode {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 py-16">
      <div className="max-w-4xl text-center">
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-brand/40 bg-brand/10 px-4 py-1.5 text-xs font-medium uppercase tracking-wider text-brand-light">
          <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
          Phase 0 · Scaffold
        </div>

        <h1 className="bg-gradient-to-r from-brand-light via-white to-brand-light bg-clip-text text-5xl font-bold tracking-tight text-transparent sm:text-6xl">
          FraudShield MLOps
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-slate-300">
          Dashboard coming soon. An end-to-end MLOps platform for real-time
          fraud detection — model serving, drift monitoring, auto-retraining,
          and live observability.
        </p>

        <div className="mt-12 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {services.map((svc) => (
            <div
              key={svc.name}
              className="group rounded-xl border border-slate-700/60 bg-slate-900/60 p-4 text-left shadow-sm transition hover:border-brand/60 hover:shadow-brand/10"
            >
              <div className="text-sm font-semibold text-slate-100">
                {svc.name}
              </div>
              <div className="mt-1 text-xs text-slate-400">{svc.role}</div>
              <div className="mt-3 font-mono text-[11px] text-slate-500 group-hover:text-brand-light">
                {svc.port}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-12 text-xs text-slate-500">
          <span className="font-mono">curl localhost:8000/health</span> · See
          README for the full quick-start.
        </div>
      </div>
    </main>
  );
}
