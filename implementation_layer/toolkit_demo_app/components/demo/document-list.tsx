"use client";

import { motion, AnimatePresence } from "motion/react";
import {
  FileText,
  CheckCircle,
  Loader2,
  AlertCircle,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export interface IndexedDocument {
  filename: string;
  chunkCount: number;
  status: "indexed" | "processing" | "error";
}

interface DocumentListProps {
  documents: IndexedDocument[];
  onRemove?: (filename: string) => void;
  className?: string;
}

export function DocumentList({
  documents,
  onRemove,
  className,
}: DocumentListProps) {
  if (documents.length === 0) {
    return null;
  }

  const totalChunks = documents
    .filter((d) => d.status === "indexed")
    .reduce((sum, d) => sum + d.chunkCount, 0);

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium">
          Indexed Documents ({documents.length})
        </h4>
        <span className="text-muted-foreground text-xs">
          {totalChunks} chunks total
        </span>
      </div>

      <div className="space-y-2">
        <AnimatePresence mode="popLayout">
          {documents.map((doc, index) => (
            <motion.div
              key={doc.filename}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ delay: index * 0.05 }}
              className={cn(
                "flex items-center gap-3 rounded-lg border p-3",
                doc.status === "indexed" &&
                  "border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950",
                doc.status === "processing" &&
                  "border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950",
                doc.status === "error" &&
                  "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950",
              )}
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/50 dark:bg-black/20">
                {doc.status === "indexed" && (
                  <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400" />
                )}
                {doc.status === "processing" && (
                  <Loader2 className="h-4 w-4 animate-spin text-blue-600 dark:text-blue-400" />
                )}
                {doc.status === "error" && (
                  <AlertCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
                )}
              </div>

              <FileText className="text-muted-foreground h-4 w-4 shrink-0" />

              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{doc.filename}</p>
                <p className="text-muted-foreground text-xs">
                  {doc.status === "indexed" && `${doc.chunkCount} chunks`}
                  {doc.status === "processing" && "Processing..."}
                  {doc.status === "error" && "Failed to index"}
                </p>
              </div>

              {onRemove && doc.status !== "processing" && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0"
                  onClick={() => onRemove(doc.filename)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

interface DocumentListCompactProps {
  documents: IndexedDocument[];
  className?: string;
}

export function DocumentListCompact({
  documents,
  className,
}: DocumentListCompactProps) {
  const indexed = documents.filter((d) => d.status === "indexed").length;
  const processing = documents.filter((d) => d.status === "processing").length;
  const errors = documents.filter((d) => d.status === "error").length;

  return (
    <div className={cn("flex items-center gap-4 text-sm", className)}>
      {indexed > 0 && (
        <span className="flex items-center gap-1.5 text-green-600 dark:text-green-400">
          <CheckCircle className="h-4 w-4" />
          {indexed} indexed
        </span>
      )}
      {processing > 0 && (
        <span className="flex items-center gap-1.5 text-blue-600 dark:text-blue-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          {processing} processing
        </span>
      )}
      {errors > 0 && (
        <span className="flex items-center gap-1.5 text-red-600 dark:text-red-400">
          <AlertCircle className="h-4 w-4" />
          {errors} failed
        </span>
      )}
    </div>
  );
}
