"use client";

import { Input } from "@/components/ui/input";
import {
  type ReportModelKind,
  reportModelNames,
  useServerModels,
} from "@/lib/server-model-store";
import { type ComponentProps, useId } from "react";

/**
 * A model field of the report demos that suggests the names their routes accept: the
 * server's list for this user (`/model-settings/server`, team-only names for the team
 * only). It stays free text: left empty it runs the server's model, and the route still
 * refuses a name it does not offer.
 */
export function ModelNameInput({
  kind,
  ...props
}: Omit<ComponentProps<typeof Input>, "list"> & { kind: ReportModelKind }) {
  const id = useId();
  const names = reportModelNames(useServerModels(), kind);
  return (
    <>
      <Input
        {...props}
        list={names.length > 0 ? id : undefined}
        autoComplete="off"
      />
      {names.length > 0 && (
        <datalist id={id}>
          {names.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      )}
    </>
  );
}
