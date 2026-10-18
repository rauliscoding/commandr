import {
  CircleCheck,
  CircleHelp,
  CircleX,
  Info,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/cn";

/** The five states used everywhere (design-system.md § Status language). */
export type Status = "ok" | "warn" | "fail" | "unknown" | "info";

const STYLE: Record<Status, { icon: LucideIcon; className: string }> = {
  ok: { icon: CircleCheck, className: "bg-ok-bg text-ok-fg border-ok-border" },
  warn: { icon: TriangleAlert, className: "bg-warn-bg text-warn-fg border-warn-border" },
  fail: { icon: CircleX, className: "bg-fail-bg text-fail-fg border-fail-border" },
  unknown: { icon: CircleHelp, className: "bg-unknown-bg text-unknown-fg border-unknown-border" },
  info: { icon: Info, className: "bg-info-bg text-info-fg border-info-border" },
};

/** Icon + word + colour: never colour alone. */
export function StatusBadge({
  status,
  label,
  className,
}: {
  status: Status;
  label: string;
  className?: string;
}) {
  const { icon: Icon, className: tone } = STYLE[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-xs font-medium",
        tone,
        className,
      )}
    >
      <Icon aria-hidden="true" className="size-3.5" />
      {label}
    </span>
  );
}
