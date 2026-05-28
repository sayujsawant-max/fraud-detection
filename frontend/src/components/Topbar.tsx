/**
 * Topbar — shows live API/model status + external service links.
 *
 * Polls the FastAPI ``/ready`` and ``/v1/model/info`` endpoints every 30
 * seconds so the dashboard's "is the backend alive?" signal is always
 * fresh without spamming the network.
 */

"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { EXTERNAL_LINKS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { ModelInfo, ReadyResponse } from "@/types";
import { Badge } from "@/components/ui/Badge";

type Status = "checking" | "ok" | "down";

type TopbarProps = {
  onOpenMobileNav: () => void;
};

export function Topbar({ onOpenMobileNav }: TopbarProps) {
  const [status, setStatus] = useState<Status>("checking");
  const [model, setModel] = useState<ModelInfo | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function ping() {
      try {
        const ready: ReadyResponse = await api.ready();
        if (cancelled) return;
        setStatus(ready.status === "ok" ? "ok" : "down");

        try {
          const info = await api.modelInfo();
          if (!cancelled) setModel(info);
        } catch {
          if (!cancelled) setModel(null);
        }
      } catch {
        if (!cancelled) setStatus("down");
      }
    }

    void ping();
    const id = window.setInterval(ping, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const statusTone: Record<Status, "muted" | "success" | "danger"> = {
    checking: "muted",
    ok: "success",
    down: "danger",
  };
  const statusLabel: Record<Status, string> = {
    checking: "Checking…",
    ok: "API online",
    down: "API offline",
  };

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-surface-border/60 bg-surface-800/80 px-4 backdrop-blur sm:px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onOpenMobileNav}
          className="grid h-9 w-9 place-items-center rounded-lg border border-surface-border/60 bg-surface-700/40 text-slate-300 hover:bg-surface-600/40 lg:hidden"
          aria-label="Open navigation"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-4 w-4"
          >
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>

        <Badge tone={statusTone[status]}>
          <span
            aria-hidden
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              status === "ok" && "bg-accent-green animate-pulse",
              status === "down" && "bg-accent-red",
              status === "checking" && "bg-slate-400",
            )}
          />
          {statusLabel[status]}
        </Badge>

        {model ? (
          <Badge tone="brand" className="hidden sm:inline-flex">
            {model.model_name}@{model.model_version}
          </Badge>
        ) : null}
      </div>

      <nav className="flex items-center gap-1 text-xs">
        <ExternalLink href={EXTERNAL_LINKS.apiDocs} label="API Docs" />
        <ExternalLink href={EXTERNAL_LINKS.mlflow} label="MLflow" />
        <ExternalLink href={EXTERNAL_LINKS.prefect} label="Prefect" />
        <ExternalLink href={EXTERNAL_LINKS.grafana} label="Grafana" />
      </nav>
    </header>
  );
}

function ExternalLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="hidden rounded-md px-2.5 py-1.5 text-slate-300 hover:bg-surface-600/40 hover:text-slate-100 sm:inline-flex"
    >
      {label}
      <span aria-hidden className="ml-1 text-slate-500">
        ↗
      </span>
    </a>
  );
}
