import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-surface-default-tertiary text-onSurface-default-secondary",
        secondary:
          "border-transparent bg-surface-default-fg-secondary text-onSurface-default-secondary",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground",
        outline:
          "border-memBorder-primary bg-transparent text-onSurface-default-secondary",
        lime: "border-transparent bg-sentry-lime/15 text-sentry-lime before:inline-block before:size-[5px] before:rounded-full before:bg-sentry-lime before:mr-1.5",
        pink: "border-transparent bg-sentry-pink/15 text-sentry-pink before:inline-block before:size-[5px] before:rounded-full before:bg-sentry-pink before:mr-1.5",
        violet:
          "border-transparent bg-sentry-violet/20 text-[#a89fe0] before:inline-block before:size-[5px] before:rounded-full before:bg-sentry-violet before:mr-1.5",
        success:
          "border-transparent bg-sentry-success/15 text-[#4cc38a] before:inline-block before:size-[5px] before:rounded-full before:bg-[#4cc38a] before:mr-1.5",
        warning:
          "border-transparent bg-sentry-warning/15 text-[#f5a623] before:inline-block before:size-[5px] before:rounded-full before:bg-[#f5a623] before:mr-1.5",
        danger:
          "border-transparent bg-sentry-danger/15 text-[#e5484d] before:inline-block before:size-[5px] before:rounded-full before:bg-[#e5484d] before:mr-1.5",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends
    React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
