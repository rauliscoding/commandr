import * as Dialog from "@radix-ui/react-dialog";
import { useCallback, useRef, useState, type FormEvent, type ReactNode } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

import { Button } from "./Button";
import { FormError, TextField } from "./Field";

const REAUTH_URL = "/api/auth/browser/v1/auth/reauthenticate";

/** The API's answer when a sensitive action needs the password again. */
export function isReauthRequired(e: unknown): boolean {
  return (
    e instanceof ApiError &&
    e.status === 401 &&
    (e.data as { code?: string } | null)?.code === "reauthentication_required"
  );
}

function ReauthDialog({ open, onDone }: { open: boolean; onDone: (ok: boolean) => void }) {
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function handle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const password = String(new FormData(event.currentTarget).get("password") ?? "");
    setBusy(true);
    setError(undefined);
    try {
      await apiFetch(REAUTH_URL, { method: "POST", body: { password } });
      onDone(true);
    } catch {
      setError(t("reauth.wrong"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={(next) => !next && onDone(false)}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-overlay" />
        <Dialog.Content className="fixed inset-x-4 top-1/2 z-50 mx-auto max-w-md -translate-y-1/2 rounded-lg bg-surface p-5 shadow-overlay">
          <Dialog.Title className="text-lg font-semibold">{t("reauth.title")}</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted">
            {t("reauth.body")}
          </Dialog.Description>
          <form onSubmit={handle} noValidate className="mt-4 space-y-4">
            <FormError message={error} />
            <TextField
              name="password"
              type="password"
              label={t("auth.password")}
              autoComplete="current-password"
              required
            />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => onDone(false)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={busy}>
                {busy ? t("common.working") : t("reauth.confirm")}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/**
 * `run(fn)` calls `fn`; if the API wants the password again it asks for it and
 * retries once. Render `dialog` somewhere in the component.
 */
export function useReauth(): {
  run: <T>(fn: () => Promise<T>) => Promise<T>;
  dialog: ReactNode;
} {
  const [open, setOpen] = useState(false);
  const resolver = useRef<((ok: boolean) => void) | null>(null);

  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T> => {
    try {
      return await fn();
    } catch (e) {
      if (!isReauthRequired(e)) throw e;
      const ok = await new Promise<boolean>((resolve) => {
        resolver.current = resolve;
        setOpen(true);
      });
      if (!ok) throw e;
      return fn();
    }
  }, []);

  const dialog = (
    <ReauthDialog
      open={open}
      onDone={(ok) => {
        setOpen(false);
        resolver.current?.(ok);
        resolver.current = null;
      }}
    />
  );
  return { run, dialog };
}
