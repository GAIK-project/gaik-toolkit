"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { FileText, ChevronDown, ChevronUp, BookOpen, Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import toast from "react-hot-toast";

export interface Source {
  documentName: string;
  pageNumber: string | number | null;
  relevanceScore?: number | null;
}

interface CitationCardProps {
  answer: string;
  sources: Source[];
  isStreaming?: boolean;
  className?: string;
}

export function CitationCard({
  answer,
  sources,
  isStreaming = false,
  className,
}: CitationCardProps) {
  const [showSources, setShowSources] = useState(true);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(true);
      toast.success("Copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Failed to copy");
    }
  };

  // Group sources by document
  const groupedSources = sources.reduce<Record<string, Source[]>>((acc, source) => {
    const key = source.documentName;
    if (!acc[key]) acc[key] = [];
    acc[key].push(source);
    return acc;
  }, {});

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="text-primary h-5 w-5" />
            <CardTitle className="text-lg">Answer</CardTitle>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleCopy}
            className="h-8 w-8"
            disabled={isStreaming}
          >
            {copied ? (
              <Check className="h-4 w-4 text-green-600" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </Button>
        </div>
        {sources.length > 0 && (
          <CardDescription>
            Based on {sources.length} source{sources.length !== 1 ? "s" : ""}
          </CardDescription>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Answer text */}
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <div className="whitespace-pre-wrap text-sm leading-relaxed">
            {answer}
            {isStreaming && (
              <motion.span
                animate={{ opacity: [1, 0] }}
                transition={{ duration: 0.5, repeat: Infinity }}
                className="bg-primary ml-0.5 inline-block h-4 w-2"
              />
            )}
          </div>
        </div>

        {/* Sources section */}
        {sources.length > 0 && (
          <div className="border-t pt-4">
            <button
              onClick={() => setShowSources(!showSources)}
              className="flex w-full items-center justify-between text-sm font-medium"
            >
              <span className="flex items-center gap-2">
                <FileText className="text-muted-foreground h-4 w-4" />
                Sources ({Object.keys(groupedSources).length} document
                {Object.keys(groupedSources).length !== 1 ? "s" : ""})
              </span>
              {showSources ? (
                <ChevronUp className="text-muted-foreground h-4 w-4" />
              ) : (
                <ChevronDown className="text-muted-foreground h-4 w-4" />
              )}
            </button>

            <AnimatePresence>
              {showSources && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="mt-3 space-y-2">
                    {Object.entries(groupedSources).map(([docName, docSources], index) => (
                      <motion.div
                        key={docName}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.05 }}
                        className="bg-muted/50 flex items-start gap-3 rounded-lg p-3"
                      >
                        <div className="bg-primary/10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full">
                          <FileText className="text-primary h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">{docName}</p>
                          <div className="mt-1 flex flex-wrap gap-1.5">
                            {docSources.map((source, i) => (
                              <Badge
                                key={i}
                                variant="secondary"
                                className="text-xs"
                              >
                                {source.pageNumber !== null && source.pageNumber !== "unknown"
                                  ? `Page ${source.pageNumber}`
                                  : `Chunk ${i + 1}`}
                                {source.relevanceScore !== null &&
                                  source.relevanceScore !== undefined && (
                                    <span className="text-muted-foreground ml-1">
                                      ({Math.round(source.relevanceScore * 100)}%)
                                    </span>
                                  )}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface StreamingAnswerProps {
  chunks: string[];
  isComplete: boolean;
  className?: string;
}

export function StreamingAnswer({ chunks, isComplete, className }: StreamingAnswerProps) {
  const answer = chunks.join("");

  return (
    <div className={cn("whitespace-pre-wrap text-sm leading-relaxed", className)}>
      {answer}
      {!isComplete && (
        <motion.span
          animate={{ opacity: [1, 0] }}
          transition={{ duration: 0.5, repeat: Infinity }}
          className="bg-primary ml-0.5 inline-block h-4 w-2"
        />
      )}
    </div>
  );
}
