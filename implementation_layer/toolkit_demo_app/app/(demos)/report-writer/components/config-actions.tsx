"use client";

import { Button } from "@/components/ui/button";
import { Download, Loader2, Upload, Zap } from "lucide-react";
import { useRef, useState } from "react";
import toast from "react-hot-toast";

interface ConfigActionsProps {
  onLoadExample: () => Promise<void>;
  onUploadConfig: (config: Record<string, unknown>) => boolean;
  onDownloadConfig: () => void;
  disabled?: boolean;
  isExampleLoaded?: boolean;
}

export function ConfigActions({
  onLoadExample,
  onUploadConfig,
  onDownloadConfig,
  disabled,
  isExampleLoaded,
}: ConfigActionsProps) {
  const [loadingExample, setLoadingExample] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleLoadExample() {
    setLoadingExample(true);
    try {
      await onLoadExample();
    } finally {
      setLoadingExample(false);
    }
  }

  function handleUploadClick() {
    fileInputRef.current?.click();
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const config = JSON.parse(ev.target!.result as string);
        onUploadConfig(config);
      } catch {
        toast.error("Invalid JSON file");
      }
    };
    reader.readAsText(file);
    // Reset so the same file can be re-uploaded
    e.target.value = "";
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        variant={isExampleLoaded ? "default" : "outline"}
        size="sm"
        onClick={handleLoadExample}
        disabled={disabled || loadingExample}
      >
        {loadingExample ? (
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
        ) : (
          <Zap className="mr-2 h-3.5 w-3.5" />
        )}
        {isExampleLoaded ? "Reload Example" : "Load Example"}
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={handleUploadClick}
        disabled={disabled}
      >
        <Upload className="mr-2 h-3.5 w-3.5" />
        Upload Usecase Config
      </Button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        className="sr-only"
        onChange={handleFileChange}
      />

      <Button
        variant="outline"
        size="sm"
        onClick={onDownloadConfig}
        disabled={disabled}
      >
        <Download className="mr-2 h-3.5 w-3.5" />
        Download Usecase Config
      </Button>

      {isExampleLoaded && (
        <p className="w-full text-xs text-muted-foreground bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 dark:border-yellow-800 rounded px-2 py-1">
          Example loaded — your edits are temporary and will not be saved back to
          the example template.
        </p>
      )}
    </div>
  );
}
