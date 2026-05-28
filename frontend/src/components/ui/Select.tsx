/**
 * Select — labelled native select with consistent dark styling.
 */

import {
  forwardRef,
  type ForwardedRef,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";
import { cn } from "@/lib/utils";

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label?: string;
  hint?: string;
  options: ReadonlyArray<{ value: string; label: string }>;
};

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, label, hint, options, id, ...props }: SelectProps,
  ref: ForwardedRef<HTMLSelectElement>,
): ReactNode {
  const selectId =
    id ?? (label ? `sel-${label.replace(/\s+/g, "-").toLowerCase()}` : undefined);
  return (
    <div className="flex flex-col gap-1.5">
      {label ? (
        <label
          htmlFor={selectId}
          className="text-[11px] font-medium uppercase tracking-wider text-slate-400"
        >
          {label}
        </label>
      ) : null}
      <select
        ref={ref}
        id={selectId}
        className={cn(
          "h-9 w-full rounded-lg border border-surface-border bg-surface-700/60 px-3 text-sm text-slate-100",
          "focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {hint ? <p className="text-[11px] text-slate-500">{hint}</p> : null}
    </div>
  );
});
