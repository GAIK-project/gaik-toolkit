"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
export interface SchemaField {
  name: string;
  /** In plain words: "text", "whole number", "list of records". */
  type: string;
  required: boolean;
  nullable?: boolean;
  description: string;
  /** How a date or time is written, for example DD/MM/YYYY. */
  format?: string | null;
  allowed?: string[] | null;
  children?: SchemaField[];
}

function Rows({ fields, depth }: { fields: SchemaField[]; depth: number }) {
  return (
    <>
      {fields.map((field) => (
        <RowGroup key={`${depth}-${field.name}`} field={field} depth={depth} />
      ))}
    </>
  );
}

function RowGroup({ field, depth }: { field: SchemaField; depth: number }) {
  return (
    <>
      <tr className={cn("border-t align-top", depth > 0 && "bg-muted/30")}>
        <td
          className="px-3 py-2 font-mono text-sm"
          style={{ paddingLeft: `${0.75 + depth * 1.25}rem` }}
        >
          {depth > 0 && <span className="text-muted-foreground mr-1">↳</span>}
          {field.name}
        </td>
        <td className="px-3 py-2 text-sm whitespace-nowrap">{field.type}</td>
        <td className="px-3 py-2 text-sm">
          {field.required ? (
            <Badge>required</Badge>
          ) : (
            <span className="text-muted-foreground">optional</span>
          )}
        </td>
        <td className="space-y-1 px-3 py-2 text-sm">
          {field.description && <p>{field.description}</p>}
          {field.format && (
            <p className="flex items-center gap-1">
              <span className="text-muted-foreground text-xs">format:</span>
              <Badge variant="outline" className="font-mono">
                {field.format}
              </Badge>
            </p>
          )}
          {field.allowed && field.allowed.length > 0 && (
            <p className="flex flex-wrap items-center gap-1">
              <span className="text-muted-foreground text-xs">one of:</span>
              {field.allowed.map((value) => (
                <Badge key={value} variant="outline" className="font-mono">
                  {value}
                </Badge>
              ))}
            </p>
          )}
        </td>
      </tr>
      {field.children && field.children.length > 0 && (
        <Rows fields={field.children} depth={depth + 1} />
      )}
    </>
  );
}

/** The fields of a schema as a table: names, plain types, rules, and nested records. */
export function FieldsTable({ fields }: { fields: SchemaField[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[34rem] text-left">
        <thead>
          <tr className="bg-muted/50 text-xs tracking-wider uppercase">
            <th className="px-3 py-2 font-medium">Field</th>
            <th className="px-3 py-2 font-medium">Type</th>
            <th className="px-3 py-2 font-medium">Rule</th>
            <th className="px-3 py-2 font-medium">
              Meaning and allowed values
            </th>
          </tr>
        </thead>
        <tbody>
          <Rows fields={fields} depth={0} />
        </tbody>
      </table>
    </div>
  );
}
