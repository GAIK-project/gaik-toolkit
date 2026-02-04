"use client";

import { cn } from "@/lib/utils";
import type { SSEStep } from "@/lib/sse";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, ChevronRight, Code2 } from "lucide-react";
import { useState } from "react";

interface PipelineLogViewerProps {
  steps: SSEStep[];
}

export function PipelineLogViewer({ steps }: PipelineLogViewerProps) {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

  const toggleStep = (stepNum: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepNum)) {
        next.delete(stepNum);
      } else {
        next.add(stepNum);
      }
      return next;
    });
  };

  return (
    <div className="space-y-2">
      {steps.map((step) => {
        const hasDetails = !!step.details;
        const isExpanded = expandedSteps.has(step.step);

        return (
          <div
            key={step.step}
            className={cn(
              "rounded-lg border transition-colors",
              step.status === "completed" &&
                "border-success/30 bg-success/5",
              step.status === "in_progress" && "border-primary/30 bg-primary/5",
              step.status === "error" &&
                "border-destructive/30 bg-destructive/5",
              step.status === "pending" && "border-muted",
            )}
          >
            <button
              type="button"
              onClick={() => hasDetails && toggleStep(step.step)}
              disabled={!hasDetails}
              className={cn(
                "flex w-full items-center gap-3 p-3 text-left",
                hasDetails && "hover:bg-muted/30 cursor-pointer",
              )}
            >
              {/* Status indicator */}
              <div
                className={cn(
                  "h-2 w-2 shrink-0 rounded-full",
                  step.status === "completed" && "bg-success",
                  step.status === "in_progress" && "bg-primary animate-pulse",
                  step.status === "error" && "bg-destructive",
                  step.status === "pending" && "bg-muted-foreground/30",
                )}
              />

              <span className="flex-1 text-sm font-medium">{step.name}</span>

              {step.message && (
                <span className="text-muted-foreground text-xs">
                  {step.message}
                </span>
              )}

              {hasDetails && (
                <span className="text-muted-foreground">
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </span>
              )}
            </button>

            <AnimatePresence>
              {hasDetails && isExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="px-3 pb-3">
                    <div className="bg-muted/50 rounded-md">
                      <div className="border-muted flex items-center gap-2 border-b px-3 py-2">
                        <Code2 className="text-muted-foreground h-4 w-4" />
                        <span className="text-muted-foreground text-xs font-medium">
                          {step.details!.title}
                        </span>
                      </div>
                      <pre className="max-h-[300px] overflow-x-auto overflow-y-auto p-3 font-mono text-xs">
                        <code>{step.details!.content}</code>
                      </pre>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
