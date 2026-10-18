/**
 * Minimal i18n: every user-facing string goes through `t()` from day one, so
 * adding Portuguese is a translation file, not a refactor. Swap for i18next if
 * plurals or interpolation outgrow this.
 */
import { en } from "@/locales/en";

// Other languages must have every key, with any wording.
type Messages = Record<keyof typeof en, string>;
export type MessageKey = keyof Messages;

const catalogues: Record<string, Messages> = { en };

let active: Messages = en;

export function setLanguage(lang: string): void {
  active = catalogues[lang] ?? en;
}

export function t(key: MessageKey, vars?: Record<string, string | number>): string {
  let text: string = active[key] ?? en[key];
  if (vars) {
    for (const [name, value] of Object.entries(vars))
      text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}
