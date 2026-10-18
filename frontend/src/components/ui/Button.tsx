import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap " +
    "transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-55 " +
    "min-h-9 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-contrast hover:bg-primary-hover",
        secondary: "border border-border-strong bg-surface text-fg hover:bg-surface-sunken",
        ghost: "text-fg hover:bg-surface-sunken",
        danger: "border border-fail-border bg-surface text-fail-fg hover:bg-fail-bg",
      },
      size: {
        sm: "px-3 text-sm",
        md: "px-4 text-sm",
        lg: "min-h-11 px-5 text-base",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof button> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, type = "button", ...props },
  ref,
) {
  return (
    <button ref={ref} type={type} className={cn(button({ variant, size }), className)} {...props} />
  );
});
