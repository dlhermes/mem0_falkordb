import { Plus, RefreshCw, SearchCode, Trash, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";

interface EventBadgeProps {
  event: string;
  type?: string;
  count?: number;
  label?: string;
  icon?: React.ElementType;
  showIcon?: boolean;
  variant?: "primary" | "secondary";
}

type BadgeVariant = "add" | "update" | "retrieved" | "delete" | "user";

const getBadgeConfig = (
  type: string,
): { variant: BadgeVariant; icon: React.ElementType } => {
  switch (type.toUpperCase()) {
    case "ADD":
      return { variant: "add", icon: Plus };
    case "UPDATE":
      return { variant: "update", icon: RefreshCw };
    case "SEARCH":
    case "GET_ALL":
    case "GET":
      return { variant: "retrieved", icon: SearchCode };
    case "DELETE":
      return { variant: "delete", icon: Trash };
    case "USER":
    case "USERS":
      return { variant: "user", icon: UserRound };
    default:
      return { variant: "add", icon: Plus };
  }
};

export function EventBadge({
  event,
  type,
  count,
  label,
  icon,
  showIcon = true,
  variant = "primary",
}: EventBadgeProps) {
  const resolvedType = (type ?? event).toUpperCase();
  const { variant: badgeVariant, icon: DefaultIcon } =
    getBadgeConfig(resolvedType);
  const Icon = icon ?? DefaultIcon;
  const content = label ?? (typeof count === "number" ? String(count) : "");

  if (count === 0 && !label) {
    return null;
  }

  const badgeSurface: Record<BadgeVariant, string> = {
    add: "bg-sentry-success/15 text-[#4cc38a]",
    update: "bg-sentry-lime/15 text-sentry-lime",
    retrieved: "bg-sentry-violet/20 text-[#a89fe0]",
    delete: "bg-sentry-danger/15 text-[#e5484d]",
    user: "bg-sentry-pink/15 text-sentry-pink",
  };

  return (
    <div
      className={cn(
        "inline-flex min-w-0 max-w-full items-center justify-center gap-1 overflow-hidden rounded-full px-2 py-0.5",
        variant === "secondary"
          ? "bg-surface-default-fg-secondary text-onSurface-default-secondary"
          : badgeSurface[badgeVariant],
      )}
      aria-label={`${event} ${badgeVariant} count`}
    >
      {showIcon && <Icon className="size-3.5 shrink-0 text-current" />}
      {content && (
        <span className="min-w-0 truncate font-dm-mono text-xs font-normal leading-[18px] text-current">
          {content}
        </span>
      )}
    </div>
  );
}
