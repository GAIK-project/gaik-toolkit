"use client";

import { useId, useState, type ReactNode } from "react";
import { Icon } from "@/components/icons";
import type { Dict } from "@/lib/i18n";
import { ENV_NAME_RE, type EnvLayout, type EnvSection, type EnvVariable, type ExtraVariable } from "@/lib/env-file";

/**
 * The values for the package's `.env`, asked where the deployable package is
 * taken. The variables come from the package's `.env.example`; the user may
 * add others (a search API's key the example does not list yet).
 *
 * A generated `.env.example` lists every provider the toolkit knows. Where the
 * package's config says which one it uses (`layout.kind === "grouped"`), that
 * provider's section and the external services' are shown, with what the
 * package cannot run without marked, and the rest is behind one disclosure.
 *
 * Nothing typed here leaves the page: the parent keeps the values in React
 * state, writes them into the downloaded zip in the browser (lib/zip-env) and
 * drops them when the PoC tab is left. No input has a name, so no form post
 * or password manager picks them up, and autocomplete is off.
 */
export function PocEnvForm({
  layout,
  values,
  extra,
  onValue,
  onExtra,
  problem,
  t,
  children,
}: {
  layout: EnvLayout;
  values: Record<string, string>;
  extra: readonly ExtraVariable[];
  onValue: (name: string, value: string) => void;
  onExtra: (extra: ExtraVariable[]) => void;
  /** The download with these values failed. */
  problem?: string | null;
  t: Dict;
  /** The download control, where the step has none of its own. */
  children?: ReactNode;
}) {
  const id = useId();
  const [shown, setShown] = useState<Record<string, boolean>>({});
  const toggle = (key: string) => setShown((now) => ({ ...now, [key]: !now[key] }));

  const secret = (key: string, value: string, label: string, placeholder: string, set: (v: string) => void) => (
    <span className="relative block">
      <input
        id={`${id}-${key}`}
        type={shown[key] ? "text" : "password"}
        value={value}
        onChange={(e) => set(e.target.value)}
        placeholder={placeholder}
        aria-label={label}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        spellCheck={false}
        data-1p-ignore
        data-lpignore="true"
        className="input-field pr-10 font-mono text-xs"
        data-testid="poc-env-value"
        data-name={key}
      />
      <button
        type="button"
        onClick={() => toggle(key)}
        aria-label={shown[key] ? t.pocEnvHide : t.pocEnvShow}
        aria-pressed={Boolean(shown[key])}
        title={shown[key] ? t.pocEnvHide : t.pocEnvShow}
        className="absolute inset-y-0 right-0 flex w-9 items-center justify-center rounded-md text-text-muted transition-colors hover:text-text"
        data-testid="poc-env-toggle"
      >
        <Icon name={shown[key] ? "eyeOff" : "eye"} size={16} />
      </button>
    </span>
  );

  const needed = new Set(layout.kind === "grouped" ? layout.needed : []);
  const rows = (variables: readonly EnvVariable[], mark: (variable: EnvVariable) => string) =>
    variables.length > 0 && (
      <ul className="flex flex-col gap-2.5">
        {variables.map((variable) => {
          const marked = mark(variable);
          return (
            <li
              key={variable.name}
              className="grid gap-1 @md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] @md:gap-3"
              data-needed={needed.has(variable.name) ? "true" : undefined}
            >
              <label htmlFor={`${id}-${variable.name}`} className="min-w-0 pt-1.5">
                <span className="block break-all font-mono text-xs font-medium text-text">{variable.name}</span>
                {(variable.help || marked) && (
                  <span className="block text-xs text-text-muted">
                    {marked && (
                      <span className={needed.has(variable.name) ? "font-medium text-text-secondary" : undefined}>
                        {marked}
                      </span>
                    )}
                    {marked && variable.help ? " · " : ""}
                    {variable.help}
                  </span>
                )}
              </label>
              {secret(variable.name, values[variable.name] ?? "", variable.name, variable.example, (v) =>
                onValue(variable.name, v),
              )}
            </li>
          );
        })}
      </ul>
    );
  const sectionOf = (section: EnvSection, mark: (variable: EnvVariable) => string) => (
    <section
      key={`${section.title ?? ""}:${section.variables[0]?.line}`}
      className="flex flex-col gap-2"
      data-testid="poc-env-section"
    >
      {section.title && <h4 className="text-xs font-semibold text-text">{section.title}</h4>}
      {rows(section.variables, mark)}
    </section>
  );

  return (
    <div className="flex flex-col gap-3" data-testid="poc-env-form">
      <p className="flex items-start gap-1.5 text-xs text-text-secondary" data-testid="poc-env-note">
        <Icon name="lock" size={13} className="mt-0.5 text-text-muted" />
        <span>{t.pocEnvNote}</span>
      </p>
      {layout.kind === "flat"
        ? rows(layout.variables, (variable) => (variable.optional ? t.pocEnvOptional : ""))
        : layout.shown.map((section) =>
            sectionOf(section, (variable) => (needed.has(variable.name) ? t.pocEnvNeeded : "")),
          )}
      {layout.kind === "grouped" && layout.restCount > 0 && (
        <details className="group/rest" data-testid="poc-env-rest">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 py-1 text-xs font-medium text-text-secondary transition-colors hover:text-text [&::-webkit-details-marker]:hidden">
            <Icon
              name="chevronRight"
              size={13}
              className="transition-transform duration-150 ease-out group-open/rest:rotate-90"
            />
            {t.pocEnvRest.replace("{n}", String(layout.restCount))}
          </summary>
          <div className="mt-2 flex flex-col gap-3">{layout.rest.map((section) => sectionOf(section, () => ""))}</div>
        </details>
      )}
      {extra.length > 0 && (
        <ul className="flex flex-col gap-2.5">
          {extra.map((item, index) => {
            const invalid = item.name.trim() !== "" && !ENV_NAME_RE.test(item.name.trim());
            const set = (change: Partial<ExtraVariable>) =>
              onExtra(extra.map((e, i) => (i === index ? { ...e, ...change } : e)));
            return (
              <li key={index} className="grid gap-1 @md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] @md:gap-3">
                <span className="min-w-0">
                  <input
                    value={item.name}
                    onChange={(e) => set({ name: e.target.value.toUpperCase().replace(/\s+/g, "_") })}
                    placeholder="TAVILY_API_KEY"
                    aria-label={t.pocEnvName}
                    aria-invalid={invalid || undefined}
                    autoComplete="off"
                    spellCheck={false}
                    className="input-field font-mono text-xs"
                    data-testid="poc-env-extra-name"
                  />
                  {invalid && <span className="mt-0.5 block text-xs text-danger-text">{t.pocEnvNameInvalid}</span>}
                </span>
                <span className="flex min-w-0 items-start gap-1">
                  <span className="min-w-0 flex-1">
                    {secret(`extra-${index}`, item.value, t.pocEnvValue, "", (v) => set({ value: v }))}
                  </span>
                  <button
                    type="button"
                    onClick={() => onExtra(extra.filter((_, i) => i !== index))}
                    aria-label={t.pocEnvRemove}
                    title={t.pocEnvRemove}
                    className="flex h-[34px] w-8 shrink-0 items-center justify-center rounded-md text-text-muted transition-colors hover:text-danger-text"
                  >
                    <Icon name="trash2" size={16} />
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => onExtra([...extra, { name: "", value: "" }])}
          className="inline-flex items-center gap-1 rounded-md py-1 text-xs font-medium text-text-secondary underline-offset-2 transition-colors hover:text-text hover:underline"
          data-testid="poc-env-add"
        >
          <Icon name="plus" size={13} />
          {t.pocEnvAdd}
        </button>
        {children && <span className="ml-auto">{children}</span>}
      </div>
      {problem && (
        <p className="text-xs text-danger-text" role="alert" data-testid="poc-env-problem">
          {problem}
        </p>
      )}
    </div>
  );
}
