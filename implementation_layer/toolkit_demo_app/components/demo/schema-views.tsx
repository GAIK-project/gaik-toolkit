"use client";

import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ReactNode } from "react";
import { FieldsTable, type SchemaField } from "./schema-fields-table";

/** A tab that a view adds to the ones it has: a value, a heading and what it shows. */
export interface ExtraTab {
  value: string;
  label: string;
  content: ReactNode;
}

/** What the extraction schema is, in the three forms the demos show. */
export interface SchemaViewData {
  schema_name: string;
  structure_type: string;
  schema_code: string;
  /** The requirements the schema was built from, as JSON. */
  requirements_json?: string;
  field_table?: SchemaField[];
}

function Code({ text }: { text: string }) {
  return (
    <pre className="bg-muted/40 max-h-96 overflow-auto rounded-lg border p-3 text-xs">
      <code>{text}</code>
    </pre>
  );
}

/**
 * The tabs of a schema: its fields as a table, the Python schema, and the requirements.json it
 * was built from. Each is shown only when there is something to show.
 */
export function schemaTabs(
  schema: SchemaViewData,
  structureText?: string,
): ExtraTab[] {
  const tabs: ExtraTab[] = [];
  if (schema.field_table && schema.field_table.length > 0) {
    tabs.push({
      value: "schema-fields",
      label: "Fields",
      content: (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs">{schema.schema_name}</span>
            <Badge variant="secondary" className="font-mono font-normal">
              {schema.structure_type}
            </Badge>
          </div>
          {structureText && (
            <p className="text-muted-foreground text-xs">{structureText}</p>
          )}
          <FieldsTable fields={schema.field_table} />
        </div>
      ),
    });
  }
  if (schema.schema_code) {
    tabs.push({
      value: "schema-code",
      label: "Python schema",
      content: <Code text={schema.schema_code} />,
    });
  }
  if (schema.requirements_json) {
    tabs.push({
      value: "schema-requirements",
      label: "requirements.json",
      content: <Code text={schema.requirements_json} />,
    });
  }
  return tabs;
}

/** The tabs of a schema on their own, for the preview before there is a result. */
export function SchemaTabsView({ tabs }: { tabs: ExtraTab[] }) {
  if (tabs.length === 0) return null;
  return (
    <Tabs defaultValue={tabs[0].value}>
      <TabsList>
        {tabs.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value}>
            {tab.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {tabs.map((tab) => (
        <TabsContent key={tab.value} value={tab.value} className="pt-3">
          {tab.content}
        </TabsContent>
      ))}
    </Tabs>
  );
}
