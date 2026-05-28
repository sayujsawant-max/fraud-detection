/**
 * LoadingState — full-section skeleton grid for async pages.
 */

import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

type LoadingStateProps = {
  rows?: number;
};

export function LoadingState({ rows = 3 }: LoadingStateProps) {
  return (
    <Card className="px-5 py-4">
      <Skeleton className="h-4 w-32" />
      <div className="mt-4 space-y-3">
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} className="h-3 w-full" />
        ))}
      </div>
    </Card>
  );
}
