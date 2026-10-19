import { UNKNOWN } from "@/lib/format";

import { Time } from "./Time";

export interface DetailItem {
  label: string;
  value: string | null;
  kind: "text" | "time" | "code";
}

/** Label/value pairs from the API. `null` is "—": unknown is not zero. */
export function DetailList({ items }: { items: DetailItem[] }) {
  if (items.length === 0) return null;
  return (
    <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-4 gap-y-1.5 text-sm">
      {items.map((item) => (
        <div key={item.label} className="contents">
          <dt className="text-muted">{item.label}</dt>
          <dd className="min-w-0 break-words">
            {item.value === null ? (
              UNKNOWN
            ) : item.kind === "time" ? (
              <Time iso={item.value} />
            ) : item.kind === "code" ? (
              <code className="font-mono text-xs">{item.value}</code>
            ) : (
              item.value
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}
