"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Code } from "lucide-react";

interface ProcessingDetailsProps {
  schema?: string;
}

export function ProcessingDetails({ schema }: ProcessingDetailsProps) {
  const [open, setOpen] = useState(false);

  if (!schema) return null;

  // Clean up schema: remove duplicate title lines and separator lines
  const cleanedSchema = schema
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      // Remove lines that are just "=" separators or title duplicates
      if (/^=+$/.test(trimmed)) return false;
      if (trimmed === "Generated Extraction Schema") return false;
      if (trimmed === "Extraction Schema") return false;
      if (trimmed === "GENERATED PYDANTIC MODEL") return false;
      return true;
    })
    .join("\n")
    .trim();

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen(true)}
        className="text-muted-foreground h-auto gap-2 px-0 py-1 hover:bg-transparent"
      >
        <Code className="h-4 w-4" />
        View Generated Schema
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="flex max-h-[90vh] w-[90vw] max-w-5xl flex-col sm:max-w-5xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Code className="h-5 w-5" />
              Generated Extraction Schema
            </DialogTitle>
            <DialogDescription>
              Pydantic model automatically generated from your requirements
            </DialogDescription>
          </DialogHeader>

          <div className="bg-white min-h-0 flex-1 overflow-hidden rounded-md border">
            <pre className="h-full max-h-[70vh] overflow-auto whitespace-pre-wrap wrap-break-word p-4 text-xs leading-relaxed text-gray-800">
              {cleanedSchema}
            </pre>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
