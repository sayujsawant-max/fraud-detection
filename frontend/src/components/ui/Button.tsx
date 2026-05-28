/**
 * Button — a small subset of shadcn/ui's variants kept Tailwind-only.
 */

import {
  forwardRef,
  type ButtonHTMLAttributes,
  type ForwardedRef,
  type ReactNode,
} from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md" | "lg" | "icon";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children?: ReactNode;
};

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-brand text-white hover:bg-brand-dark border border-brand/70 shadow-ring",
  secondary:
    "bg-surface-600/60 text-slate-100 border border-surface-border hover:bg-surface-600",
  ghost:
    "bg-transparent text-slate-200 hover:bg-surface-600/50 border border-transparent",
  danger:
    "bg-accent-red/90 text-white hover:bg-accent-red border border-accent-red/70",
  outline:
    "bg-transparent text-brand-light border border-brand/60 hover:bg-brand/10",
};

const sizeClasses: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-9 px-4 text-sm",
  lg: "h-10 px-5 text-sm",
  icon: "h-9 w-9 p-0",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    className,
    variant = "primary",
    size = "md",
    loading = false,
    disabled,
    children,
    ...props
  }: ButtonProps,
  ref: ForwardedRef<HTMLButtonElement>,
): ReactNode {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    >
      {loading ? (
        <span
          aria-hidden
          className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-r-transparent"
        />
      ) : null}
      {children}
    </button>
  );
});
