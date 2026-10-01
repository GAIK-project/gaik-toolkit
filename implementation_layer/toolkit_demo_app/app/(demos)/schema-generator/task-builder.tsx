"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Plus, X } from "lucide-react";
import {
  FIELD_TYPES,
  MAX_BUILDER_FIELDS,
  newField,
  type BuilderField,
  type BuilderState,
  type FieldType,
  type Structure,
} from "./schema-data";

const STRUCTURES: { id: Structure; label: string; text: string }[] = [
  {
    id: "single",
    label: "One record",
    text: "one set of fields for each document",
  },
  {
    id: "list",
    label: "A list of records",
    text: "the document holds several records of one kind",
  },
  {
    id: "header-and-list",
    label: "Header + list",
    text: "document fields, plus repeated rows such as line items",
  },
];

function FieldRows({
  fields,
  onChange,
  disabled,
  label,
}: {
  fields: BuilderField[];
  onChange: (fields: BuilderField[]) => void;
  disabled: boolean;
  label: string;
}) {
  const update = (id: string, patch: Partial<BuilderField>) =>
    onChange(
      fields.map((field) => (field.id === id ? { ...field, ...patch } : field)),
    );
  return (
    <div className="space-y-2">
      {fields.map((field, index) => (
        <div
          key={field.id}
          className="grid gap-2 rounded-lg border p-2 sm:grid-cols-[minmax(0,1fr)_9.5rem_auto]"
        >
          <Input
            value={field.name}
            onChange={(event) => update(field.id, { name: event.target.value })}
            placeholder="Field name"
            maxLength={60}
            disabled={disabled}
            aria-label={`${label} ${index + 1}: name`}
          />
          <Select
            value={field.type}
            onValueChange={(value) =>
              update(field.id, { type: value as FieldType })
            }
            disabled={disabled}
          >
            <SelectTrigger aria-label={`${label} ${index + 1}: type`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FIELD_TYPES.map((type) => (
                <SelectItem key={type} value={type}>
                  {type}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex items-center gap-2 sm:justify-end">
            <Label className="flex items-center gap-1.5 text-xs">
              <Switch
                checked={field.required}
                onCheckedChange={(required) => update(field.id, { required })}
                disabled={disabled}
                aria-label={`${label} ${index + 1}: required`}
              />
              required
            </Label>
            <Button
              type="button"
              size="icon-xs"
              variant="ghost"
              aria-label="Remove field"
              disabled={disabled}
              onClick={() => onChange(fields.filter((f) => f.id !== field.id))}
            >
              <X />
            </Button>
          </div>
          <Input
            value={field.description}
            onChange={(event) =>
              update(field.id, { description: event.target.value })
            }
            placeholder="What it means (optional)"
            maxLength={200}
            disabled={disabled}
            className="sm:col-span-3"
            aria-label={`${label} ${index + 1}: meaning`}
          />
          {field.type === "choice" && (
            <Input
              value={field.choices}
              onChange={(event) =>
                update(field.id, { choices: event.target.value })
              }
              placeholder="Allowed values, separated by commas"
              maxLength={200}
              disabled={disabled}
              className="sm:col-span-3"
              aria-label={`${label} ${index + 1}: allowed values`}
            />
          )}
        </div>
      ))}
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={disabled || fields.length >= MAX_BUILDER_FIELDS}
        onClick={() => onChange([...fields, newField()])}
      >
        <Plus className="size-4" />
        Add field
      </Button>
    </div>
  );
}

/** Builds the extraction task from fields, instead of writing it in words. */
export function TaskBuilder({
  state,
  onChange,
  disabled,
}: {
  state: BuilderState;
  onChange: (state: BuilderState) => void;
  disabled: boolean;
}) {
  const showHeader = state.structure !== "list";
  const showList = state.structure !== "single";
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="builder-subject">What do you extract from?</Label>
        <Input
          id="builder-subject"
          value={state.subject}
          onChange={(event) =>
            onChange({ ...state, subject: event.target.value })
          }
          placeholder="e.g. an invoice, a purchase request"
          maxLength={80}
          disabled={disabled}
        />
      </div>

      <div className="space-y-1.5">
        <Label>How is the data shaped?</Label>
        <ToggleGroup
          type="single"
          value={state.structure}
          onValueChange={(value) =>
            value && onChange({ ...state, structure: value as Structure })
          }
          className="flex-wrap justify-start"
          aria-label="Structure"
        >
          {STRUCTURES.map((structure) => (
            <ToggleGroupItem
              key={structure.id}
              value={structure.id}
              className="px-3"
              title={structure.text}
            >
              {structure.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <p className="text-muted-foreground text-xs">
          {STRUCTURES.find((s) => s.id === state.structure)?.text}.
        </p>
      </div>

      {showHeader && (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold">
            {state.structure === "single" ? "Fields" : "Header fields"}
          </h4>
          <FieldRows
            fields={state.fields}
            onChange={(fields) => onChange({ ...state, fields })}
            disabled={disabled}
            label="Field"
          />
        </div>
      )}

      {showList && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-sm font-semibold">Each list entry is one</h4>
            <Input
              value={state.listName}
              onChange={(event) =>
                onChange({ ...state, listName: event.target.value })
              }
              placeholder="e.g. line item"
              maxLength={40}
              disabled={disabled}
              className="h-8 w-44"
              aria-label="What each list entry is"
            />
          </div>
          <FieldRows
            fields={state.listFields}
            onChange={(listFields) => onChange({ ...state, listFields })}
            disabled={disabled}
            label="List field"
          />
        </div>
      )}
    </div>
  );
}
