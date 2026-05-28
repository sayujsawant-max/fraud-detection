/**
 * Input — labelled text/number input with consistent dark styling.
 */

import {
  forwardRef,
  type ForwardedRef,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import { cn } from "@/lib/utils";

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
};

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, label, hint, id, ...props }: InputProps,
  ref: ForwardedRef<HTMLInputElement>,
): ReactNode {
  const inputId =
    id ?? (label ? `inp-${label.replace(/\s+/g, "-").toLowerCase()}` : undefined);
  return (
    <div className="flex flex-col gap-1.5">
      {label ? (
        <label
          htmlFor={inputId}
          className="text-[11px] font-medium uppercase tracking-wider text-slate-400"
        >
          {label}
        </label>
      ) : null}
      <input
        ref={ref}
        id={inputId}
        className={cn(
          "h-9 w-full rounded-lg border border-surface-border bg-surface-700/60 px-3 text-sm text-slate-100",
          "placeholder:text-slate-500 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      />
      {hint ? <p className="text-[11px] text-slate-500">{hint}</p> : null}
    </div>
  );
});
