"use client";

import { cn } from "@/lib/utils";
import { CheckCircle2, CircleAlert } from "lucide-react";
import type { SchemaField } from "./use-session-schema";

function FieldRows({
  fields,
  depth = 0,
}: {
  fields: SchemaField[];
  depth?: number;
}) {
  return (
    <>
      {fields.map((field) => (
        <div key={`${depth}-${field.name}`}>
          <div
            className="grid gap-1 px-3 py-2 sm:grid-cols-[11rem_minmax(0,15rem)_minmax(0,1fr)] sm:gap-3"
            style={{ paddingLeft: `${0.75 + depth * 1.25}rem` }}
          >
            <span className="font-mono text-sm break-words">{field.name}</span>
            <span className="text-muted-foreground font-mono text-xs break-words sm:pt-0.5">
              {field.type}
            </span>
            <span className="text-muted-foreground text-sm">
              {field.description}
            </span>
          </div>
          {field.children && (
            <FieldRows fields={field.children} depth={depth + 1} />
          )}
        </div>
      ))}
    </>
  );
}

/** Says whether a schema exists for the current prompt, and shows its fields. */
export function SchemaPanel({
  fields,
  isCurrent,
}: {
  fields: SchemaField[] | null;
  isCurrent: boolean;
}) {
  if (!fields) {
    return (
      <p className="text-muted-foreground flex items-center gap-2 text-sm">
        <CircleAlert className="size-4" />
        No schema yet. Generate it from your choices, check it, then extract.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <p
        className={cn(
          "flex items-center gap-2 text-sm font-medium",
          isCurrent ? "text-green-700" : "text-amber-700",
        )}
      >
        {isCurrent ? (
          <>
            <CheckCircle2 className="size-4" />
            The schema matches your choices. It is reused for every extraction
            until you change them.
          </>
        ) : (
          <>
            <CircleAlert className="size-4" />
            You changed the fields or the prompt. Regenerate the schema before
            you extract.
          </>
        )}
      </p>
      <div
        className={cn(
          "divide-y overflow-auto rounded-lg border text-left",
          !isCurrent && "opacity-60",
        )}
      >
        <FieldRows fields={fields} />
      </div>
    </div>
  );
}
