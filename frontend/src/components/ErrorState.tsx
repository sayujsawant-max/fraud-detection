/**
 * ErrorState — friendly error card with optional retry button.
 */

import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

type ErrorStateProps = {
  title?: string;
  message?: string;
  onRetry?: () => void;
  children?: ReactNode;
};

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  children,
}: ErrorStateProps) {
  return (
    <Card className="border-accent-red/40 bg-accent-red/5 px-6 py-5">
      <div className="flex items-start gap-3">
        <div className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-full bg-accent-red/15 text-accent-red">
          !
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-slate-100">{title}</h4>
          {message ? (
            <p className="mt-1 text-sm text-slate-300">{message}</p>
          ) : null}
          {children}
          {onRetry ? (
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={onRetry}
            >
              Retry
            </Button>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
