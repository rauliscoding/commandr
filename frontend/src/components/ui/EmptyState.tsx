import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** What would be here, why it is empty, and the one action that fills it. */
export function EmptyState({
  icon: Icon,
  title,
  body,
  action,
}: {
  icon: LucideIcon;
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-16 text-center">
      <span className="mb-4 inline-flex size-12 items-center justify-center rounded-lg bg-primary-soft text-primary">
        <Icon aria-hidden="true" className="size-6" />
      </span>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-muted">{body}</p>
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  );
}
