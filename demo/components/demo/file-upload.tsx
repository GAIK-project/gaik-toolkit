"use client";

import { useCallback, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Upload, File, X, CheckCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface FileUploadProps {
  accept?: string;
  maxSize?: number; // in MB
  onFileSelect: (file: File) => void;
  onFileRemove?: () => void;
  disabled?: boolean;
  className?: string;
}

export function FileUpload({
  accept = ".pdf,.docx",
  maxSize = 10,
  onFileSelect,
  onFileRemove,
  disabled = false,
  className,
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const validateFile = useCallback(
    (file: File): boolean => {
      // Check file type
      const acceptedTypes = accept.split(",").map((t) => t.trim().toLowerCase());
      const fileExt = `.${file.name.split(".").pop()?.toLowerCase()}`;
      const isValidType = acceptedTypes.some(
        (type) => type === fileExt || file.type.includes(type.replace(".", ""))
      );

      if (!isValidType) {
        setError(`Invalid file type. Accepted: ${accept}`);
        return false;
      }

      // Check file size
      if (file.size > maxSize * 1024 * 1024) {
        setError(`File too large. Max size: ${maxSize}MB`);
        return false;
      }

      setError(null);
      return true;
    },
    [accept, maxSize]
  );

  const handleFile = useCallback(
    (file: File) => {
      if (validateFile(file)) {
        setSelectedFile(file);
        onFileSelect(file);
      }
    },
    [validateFile, onFileSelect]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);

      if (disabled) return;

      const file = e.dataTransfer.files[0];
      if (file) {
        handleFile(file);
      }
    },
    [disabled, handleFile]
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (!disabled) {
        setIsDragging(true);
      }
    },
    [disabled]
  );

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        handleFile(file);
      }
    },
    [handleFile]
  );

  const removeFile = useCallback(() => {
    setSelectedFile(null);
    setError(null);
    onFileRemove?.();
  }, [onFileRemove]);

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className={cn("w-full", className)}>
      <AnimatePresence mode="wait">
        {selectedFile ? (
          <motion.div
            key="selected"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 p-4 dark:border-green-800 dark:bg-green-950"
          >
            <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
            <File className="h-5 w-5 text-muted-foreground" />
            <div className="flex-1 min-w-0">
              <p className="truncate font-medium text-sm">{selectedFile.name}</p>
              <p className="text-xs text-muted-foreground">
                {formatFileSize(selectedFile.size)}
              </p>
            </div>
            <button
              onClick={removeFile}
              disabled={disabled}
              className="rounded-full p-1 hover:bg-green-100 dark:hover:bg-green-900 transition-colors"
              aria-label="Remove file"
            >
              <X className="h-4 w-4" />
            </button>
          </motion.div>
        ) : (
          <motion.div
            key="upload"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <label
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              className={cn(
                "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 transition-all cursor-pointer",
                isDragging
                  ? "border-primary bg-primary/5 scale-[1.02]"
                  : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50",
                disabled && "opacity-50 cursor-not-allowed",
                error && "border-destructive"
              )}
            >
              <motion.div
                animate={isDragging ? { scale: 1.1, y: -5 } : { scale: 1, y: 0 }}
                transition={{ type: "spring", stiffness: 300, damping: 20 }}
              >
                <Upload
                  className={cn(
                    "h-10 w-10",
                    isDragging ? "text-primary" : "text-muted-foreground"
                  )}
                />
              </motion.div>
              <div className="text-center">
                <p className="font-medium">
                  {isDragging ? "Drop file here" : "Drag & drop or click to upload"}
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  Supports: {accept} (max {maxSize}MB)
                </p>
              </div>
              <input
                type="file"
                accept={accept}
                onChange={handleInputChange}
                disabled={disabled}
                className="sr-only"
              />
            </label>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {error && (
          <motion.p
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="mt-2 text-sm text-destructive"
          >
            {error}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}
