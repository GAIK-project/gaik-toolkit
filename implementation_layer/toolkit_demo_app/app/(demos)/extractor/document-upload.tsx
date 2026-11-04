"use client";

import { openFileInNewTab } from "@/components/demo/file-upload";
import { cn, formatFileSize } from "@/lib/utils";
import { ExternalLink, File as FileIcon, Upload, X } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import {
  ACCEPTED_FILES,
  MAX_DOCUMENT_MB,
  MAX_DOCUMENTS,
  addDocuments,
} from "./extractor-data";

/** The documents to read: a list that grows as files are chosen or dropped. */
export function DocumentUpload({
  files,
  onChange,
  disabled = false,
}: {
  files: File[];
  onChange: (files: File[]) => void;
  disabled?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const full = files.length >= MAX_DOCUMENTS;

  function add(incoming: File[]): void {
    const { files: next, rejected } = addDocuments(files, incoming);
    if (rejected.length > 0) toast.error(rejected.join("\n"));
    if (next.length !== files.length) onChange(next);
  }

  return (
    <div className="space-y-3">
      {files.length > 0 && (
        <ul className="space-y-2" aria-label="Documents to read">
          {files.map((file, index) => (
            <li
              key={`${file.name}-${file.size}-${file.lastModified}`}
              className="border-success/30 bg-success/10 flex items-center gap-3 rounded-lg border px-4 py-2.5"
            >
              <span className="text-muted-foreground w-4 text-xs">
                {index + 1}
              </span>
              <FileIcon className="text-muted-foreground h-5 w-5 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{file.name}</p>
                <p className="text-muted-foreground text-xs">
                  {formatFileSize(file.size)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => openFileInNewTab(file)}
                className="hover:bg-success/20 rounded-full p-1 transition-colors"
                aria-label={`Open ${file.name} in a new tab`}
                title="Open in a new tab"
              >
                <ExternalLink className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => onChange(files.filter((_, i) => i !== index))}
                disabled={disabled}
                className="hover:bg-success/20 rounded-full p-1 transition-colors"
                aria-label={`Remove ${file.name}`}
              >
                <X className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {!full && (
        <label
          onDragOver={(event) => {
            event.preventDefault();
            if (!disabled) setDragging(true);
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            setDragging(false);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            if (!disabled) add(Array.from(event.dataTransfer.files));
          }}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed p-4 transition-all",
            files.length === 0 && "min-h-[176px] gap-2 p-8",
            dragging
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50",
            disabled && "cursor-not-allowed opacity-50",
          )}
        >
          <Upload
            className={cn(
              "text-muted-foreground",
              files.length === 0 ? "h-10 w-10" : "h-6 w-6",
            )}
          />
          <div className="text-center">
            <p className="font-medium">
              {dragging
                ? "Drop the files here"
                : files.length === 0
                  ? "Drag & drop or click to upload"
                  : "Add more documents"}
            </p>
            <p className="text-muted-foreground mt-1 text-sm">
              One or several files · up to {MAX_DOCUMENTS} documents ·{" "}
              {MAX_DOCUMENT_MB} MB each
            </p>
          </div>
          <input
            type="file"
            multiple
            accept={ACCEPTED_FILES}
            disabled={disabled}
            className="sr-only"
            onChange={(event) => {
              add(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
        </label>
      )}
      {full && (
        <p className="text-muted-foreground text-xs">
          {MAX_DOCUMENTS} documents is the most for one extraction. Remove one
          to add another.
        </p>
      )}
    </div>
  );
}
