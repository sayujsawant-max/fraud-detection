/**
 * EmptyState — used when a backend list endpoint returns zero rows.
 */

import Link from "next/link";
import type { ReactNode } from "react";
import { Card } from "@/components/ui/Card";

type EmptyStateProps = {
  title: string;
  description?: string;
  cta?: { href: string; label: string };
  icon?: ReactNode;
};

export function EmptyState({ title, description, cta, icon }: EmptyStateProps) {
  return (
    <Card className="flex flex-col items-center justify-center px-6 py-10 text-center">
      <div className="mb-3 grid h-10 w-10 place-items-center rounded-full bg-surface-700/60 text-brand-light">
        {icon ?? <span aria-hidden>○</span>}
      </div>
      <h4 className="text-base font-semibold text-slate-100">{title}</h4>
      {description ? (
        <p className="mt-1 max-w-md text-sm text-slate-400">{description}</p>
      ) : null}
      {cta ? (
        <Link
          href={cta.href}
          className="mt-4 inline-flex items-center gap-2 rounded-lg border border-brand/60 bg-brand/10 px-4 py-2 text-sm text-brand-light hover:bg-brand/20"
        >
          {cta.label}
        </Link>
      ) : null}
    </Card>
  );
}
