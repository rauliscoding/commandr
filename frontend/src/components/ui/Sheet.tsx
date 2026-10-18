import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useRef, type ReactNode } from "react";

import { t } from "@/lib/i18n";

/**
 * A right-hand sheet (full screen on phones). Radix Dialog gives it a real focus
 * trap and Escape to close.
 *
 * Focus return is done here: Radix only returns focus to a `Dialog.Trigger`,
 * and our sheets are opened by ordinary buttons (a card's Connect), so without
 * this a keyboard user is dropped at the top of the page on close (WCAG 2.4.3).
 */
export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const returnFocusTo = useRef<HTMLElement | null>(null);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-overlay" />
        <Dialog.Content
          onOpenAutoFocus={() => {
            // Fires before Radix moves focus in, so this is still the opener.
            returnFocusTo.current = document.activeElement as HTMLElement | null;
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            returnFocusTo.current?.focus();
          }}
          className="fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-surface shadow-overlay sm:max-w-md sm:border-l sm:border-border"
        >
          <header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
            <div className="min-w-0">
              <Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title>
              {description ? (
                <Dialog.Description className="mt-1 text-sm text-muted">
                  {description}
                </Dialog.Description>
              ) : (
                <Dialog.Description className="sr-only">{title}</Dialog.Description>
              )}
            </div>
            <Dialog.Close
              className="-mr-2 inline-flex size-9 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-sunken hover:text-fg"
              aria-label={t("common.close")}
            >
              <X aria-hidden="true" className="size-5" />
            </Dialog.Close>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">{children}</div>
          {footer ? <footer className="border-t border-border px-5 py-4">{footer}</footer> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
