"use client";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type { SourceClass } from "@/lib/report-writer/workspace";
import { cn, formatFileSize } from "@/lib/utils";
import { Download, FileText, Upload, X } from "lucide-react";

import { downloadBlob } from "./artifact-browser";

/** A file named by the spec; `file` is null until the user supplies it. */
export interface SourceRow {
  name: string;
  sourceClass: SourceClass;
  file: File | null;
}
export type SampleRow = Omit<SourceRow, "sourceClass">;

function FileLine({
  row,
  disabled,
  onRemove,
  children,
}: {
  row: SampleRow;
  disabled?: boolean;
  onRemove: () => void;
  children?: React.ReactNode;
}) {
  return (
    <li className="flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm">
      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="flex-1 truncate">{row.name}</span>
      {row.file ? (
        <span className="text-xs text-muted-foreground shrink-0">
          {formatFileSize(row.file.size)}
        </span>
      ) : (
        <span className="text-xs text-destructive shrink-0">
          missing, add this file
        </span>
      )}
      {children}
      {row.file && (
        <button
          type="button"
          title="Download"
          onClick={() => downloadBlob(row.file!, row.name)}
          className="text-muted-foreground hover:text-foreground"
        >
          <Download className="h-3.5 w-3.5" />
        </button>
      )}
      {!disabled && (
        <button
          type="button"
          title="Remove"
          onClick={onRemove}
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </li>
  );
}

function PickFiles({
  label,
  multiple,
  disabled,
  onPick,
}: {
  label: string;
  multiple?: boolean;
  disabled?: boolean;
  onPick: (files: File[]) => void;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center gap-2 rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground hover:border-muted-foreground/50 transition-colors",
        disabled && "pointer-events-none opacity-50",
      )}
    >
      <Upload className="h-4 w-4" />
      {label}
      <input
        type="file"
        multiple={multiple}
        className="sr-only"
        disabled={disabled}
        onChange={(e) => {
          onPick(Array.from(e.target.files || []));
          e.target.value = "";
        }}
      />
    </label>
  );
}

export function SourceList({
  sources,
  onSourcesChange,
  sample,
  onSampleChange,
  disabled,
}: {
  sources: SourceRow[];
  onSourcesChange: (rows: SourceRow[]) => void;
  sample: SampleRow | null;
  onSampleChange: (row: SampleRow | null) => void;
  disabled?: boolean;
}) {
  // A file whose name the spec already lists fills that row; others append.
  function addFiles(files: File[]) {
    const next = [...sources];
    for (const file of files) {
      const i = next.findIndex((r) => r.name === file.name);
      if (i >= 0) next[i] = { ...next[i], file };
      else next.push({ name: file.name, sourceClass: "primary", file });
    }
    onSourcesChange(next);
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        {sources.length > 0 && (
          <ul className="space-y-1">
            {sources.map((row, i) => (
              <FileLine
                key={row.name}
                row={row}
                disabled={disabled}
                onRemove={() => onSourcesChange(sources.filter((_, j) => j !== i))}
              >
                <button
                  type="button"
                  disabled={disabled}
                  title="Primary sources are the evidence; secondary sources give background"
                  onClick={() =>
                    onSourcesChange(
                      sources.map((r, j) =>
                        j === i
                          ? {
                              ...r,
                              sourceClass:
                                r.sourceClass === "primary" ? "secondary" : "primary",
                            }
                          : r,
                      ),
                    )
                  }
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-xs font-mono transition-colors shrink-0",
                    row.sourceClass === "primary"
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-muted text-muted-foreground",
                    disabled && "pointer-events-none opacity-50",
                  )}
                >
                  {row.sourceClass}
                </button>
              </FileLine>
            ))}
          </ul>
        )}
        <PickFiles label="Add source files" multiple disabled={disabled} onPick={addFiles} />
      </div>

      <div className="space-y-1">
        <Label className="text-sm">
          Sample report{" "}
          <span className="text-muted-foreground font-normal">
            (optional, a format reference)
          </span>
        </Label>
        {sample && (
          <ul>
            <FileLine row={sample} disabled={disabled} onRemove={() => onSampleChange(null)} />
          </ul>
        )}
        <PickFiles
          label={sample ? "Replace sample report" : "Upload sample report"}
          disabled={disabled}
          onPick={([file]) => file && onSampleChange({ name: file.name, file })}
        />
      </div>
    </div>
  );
}
