/**
 * ModelInfoBadge — compact summary of the currently-loaded model.
 *
 * Used on the Overview page and as inline context next to forms.
 */

import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { formatNumber, timeAgo } from "@/lib/utils";
import type { ModelInfo } from "@/types";

type ModelInfoBadgeProps = {
  model: ModelInfo | null;
  loading?: boolean;
};

export function ModelInfoBadge({ model, loading }: ModelInfoBadgeProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Loaded Model</CardTitle>
        <CardDescription>
          The model that is currently scoring every prediction request.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {loading || !model ? (
          <>
            <Skel label="Model name" />
            <Skel label="Version" />
            <Skel label="Stage" />
            <Skel label="Loaded" />
          </>
        ) : (
          <>
            <Field label="Model name">
              <span className="font-medium text-slate-100">{model.model_name}</span>
              {model.is_dummy ? (
                <Badge tone="warning" className="ml-2">
                  Dummy
                </Badge>
              ) : null}
            </Field>
            <Field label="Version">
              <Badge tone="brand">v{model.model_version}</Badge>
            </Field>
            <Field label="Stage / Threshold">
              <span className="text-slate-100">{model.model_stage}</span>
              <span className="ml-2 text-slate-400">
                · t = {formatNumber(model.threshold, 4)}
              </span>
            </Field>
            <Field label="Loaded">
              <span title={model.loaded_at}>{timeAgo(model.loaded_at)}</span>
            </Field>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
        {label}
      </span>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function Skel({ label }: { label: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
        {label}
      </span>
      <div className="h-5 w-24 animate-pulse rounded bg-surface-600/40" />
    </div>
  );
}
