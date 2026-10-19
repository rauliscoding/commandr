import { Check, Copy } from "lucide-react";
import { useId, useState } from "react";

import { cn } from "@/lib/cn";
import { t } from "@/lib/i18n";

/**
 * A read-only value with a copy button and a "Copied" announcement
 * (design-system.md § Copyable values). Multi-line values (code) render in a
 * <pre>; single values in a read-only input, so they can also be selected.
 */
export function CopyField({
  label,
  value,
  multiline = false,
}: {
  label: string;
  value: string;
  multiline?: boolean;
}) {
  const id = useId();
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard refused (permissions, insecure context): the value is still
      // selectable, so do nothing rather than claim it was copied.
    }
  }

  const control =
    "block w-full rounded-md border border-border-strong bg-surface-sunken px-3 py-2 font-mono text-sm text-fg";

  return (
    <div className="space-y-1.5">
      <div className="flex items-end justify-between gap-2">
        {multiline ? (
          <p id={`${id}-label`} className="text-sm font-medium">
            {label}
          </p>
        ) : (
          <label htmlFor={id} className="block text-sm font-medium">
            {label}
          </label>
        )}
        <button
          type="button"
          onClick={copy}
          // Starts with the visible word, so speech input still matches (WCAG 2.5.3).
          aria-label={`${copied ? t("copy.copied") : t("copy.copy")} ${label}`}
          className="inline-flex min-h-8 items-center gap-1.5 rounded-md px-2 text-sm text-muted hover:bg-surface-sunken hover:text-fg"
        >
          {copied ? (
            <Check aria-hidden="true" className="size-4" />
          ) : (
            <Copy aria-hidden="true" className="size-4" />
          )}
          {copied ? t("copy.copied") : t("copy.copy")}
        </button>
      </div>
      {multiline ? (
        <pre
          id={id}
          // A horizontally scrolling region must be reachable by keyboard
          // (axe: scrollable-region-focusable), so it takes focus on purpose.
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
          tabIndex={0}
          aria-labelledby={`${id}-label`}
          className={cn(control, "overflow-x-auto whitespace-pre")}
        >
          {value}
        </pre>
      ) : (
        <input
          id={id}
          readOnly
          value={value}
          onFocus={(e) => e.currentTarget.select()}
          className={control}
        />
      )}
      <p aria-live="polite" className="sr-only">
        {copied ? t("copy.copied_announcement", { label }) : ""}
      </p>
    </div>
  );
}
