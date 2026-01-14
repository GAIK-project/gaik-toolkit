"use client";

import { useState } from "react";
import { Eye, Loader2, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ExamplePreviewDialogProps {
  exampleUrl: string;
  exampleName: string;
  onUseExample: (file: File) => void;
  disabled?: boolean;
  buttonVariant?: "ghost" | "outline" | "default";
  buttonSize?: "sm" | "default" | "lg";
}

export function ExamplePreviewDialog({
  exampleUrl,
  exampleName,
  onUseExample,
  disabled = false,
  buttonVariant = "ghost",
  buttonSize = "sm",
}: ExamplePreviewDialogProps) {
  const [open, setOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  async function handleOpenDialog() {
    setOpen(true);
    setPreviewUrl(exampleUrl);
  }

  async function handleUseExample() {
    setIsLoading(true);
    try {
      const response = await fetch(exampleUrl);
      if (!response.ok) {
        throw new Error("Failed to load example file");
      }
      const blob = await response.blob();
      const file = new File([blob], exampleName, {
        type: blob.type || "application/pdf",
      });
      onUseExample(file);
      setOpen(false);
    } catch (error) {
      console.error("Failed to load example:", error);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <>
      <Button
        variant={buttonVariant}
        size={buttonSize}
        onClick={handleOpenDialog}
        disabled={disabled}
      >
        <Eye className="mr-2 h-4 w-4" />
        Example
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Example Document
            </DialogTitle>
            <DialogDescription>{exampleName}</DialogDescription>
          </DialogHeader>

          <div className="flex-1 min-h-0 overflow-hidden rounded-md border bg-muted/30">
            {previewUrl ? (
              <iframe
                src={previewUrl}
                className="w-full h-[500px]"
                title="Document preview"
              />
            ) : (
              <div className="flex items-center justify-center h-[500px]">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleUseExample} disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Loading...
                </>
              ) : (
                "Use this example"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
