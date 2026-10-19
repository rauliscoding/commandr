import { formatAbsolute, formatRelative, UNKNOWN } from "@/lib/format";

/** Relative under a day, the absolute time in the tooltip; "—" when unknown. */
export function Time({ iso, className }: { iso: string | null | undefined; className?: string }) {
  if (!iso) return <span className={className}>{UNKNOWN}</span>;
  return (
    <time dateTime={iso} title={formatAbsolute(iso)} className={className}>
      {formatRelative(iso)}
    </time>
  );
}
