import { useId, type ComponentProps, type ReactNode } from "react";

import { cn } from "@/lib/cn";
import { t } from "@/lib/i18n";

const control =
  "block w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-fg " +
  "placeholder:text-subtle aria-[invalid=true]:border-fail-fg";

/** Label above, help under the label, error under the control — all wired by id. */
function FieldShell({
  id,
  label,
  help,
  error,
  required,
  children,
}: {
  id: string;
  label: string;
  help?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
        {required ? <span className="text-muted"> {t("common.required")}</span> : null}
      </label>
      {help ? (
        <p id={`${id}-help`} className="text-sm text-muted">
          {help}
        </p>
      ) : null}
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-sm font-medium text-fail-fg">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function describedBy(id: string, help?: string, error?: string): string | undefined {
  const ids = [help ? `${id}-help` : null, error ? `${id}-error` : null].filter(Boolean);
  return ids.length ? ids.join(" ") : undefined;
}

// React 19: `ref` is an ordinary prop, so it reaches the <input> through the spread.
type TextFieldProps = ComponentProps<"input"> & {
  label: string;
  help?: string;
  error?: string;
};

export function TextField({
  label,
  help,
  error,
  required,
  className,
  id: idProp,
  ...props
}: TextFieldProps) {
  const autoId = useId();
  const id = idProp ?? autoId;
  return (
    <FieldShell id={id} label={label} help={help} error={error} required={required}>
      <input
        id={id}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, help, error)}
        className={cn(control, className)}
        {...props}
      />
    </FieldShell>
  );
}

type SelectFieldProps = ComponentProps<"select"> & {
  label: string;
  help?: string;
  error?: string;
  options: { value: string; label: string }[];
};

export function SelectField({
  label,
  help,
  error,
  required,
  options,
  className,
  id: idProp,
  ...props
}: SelectFieldProps) {
  const autoId = useId();
  const id = idProp ?? autoId;
  return (
    <FieldShell id={id} label={label} help={help} error={error} required={required}>
      <select
        id={id}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, help, error)}
        className={cn(control, className)}
        {...props}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}

/** Form-level error, announced as soon as it appears. */
export function FormError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="rounded-md border border-fail-border bg-fail-bg px-3 py-2 text-sm text-fail-fg"
    >
      {message}
    </div>
  );
}
