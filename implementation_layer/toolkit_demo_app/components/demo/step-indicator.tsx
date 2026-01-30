"use client";

import { motion } from "motion/react";
import { Check, Circle, CircleDot, X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface Step {
  id: string;
  name: string;
  status: "pending" | "in_progress" | "completed" | "error";
  message?: string | null;
}

interface StepIndicatorProps {
  steps: Step[];
  className?: string;
  orientation?: "horizontal" | "vertical";
}

export function StepIndicator({
  steps,
  className,
  orientation = "horizontal",
}: StepIndicatorProps) {
  const isHorizontal = orientation === "horizontal";

  return (
    <div
      className={cn(
        "flex",
        isHorizontal ? "flex-row items-center gap-2" : "flex-col gap-4",
        className,
      )}
    >
      {steps.map((step, index) => (
        <div
          key={step.id}
          className={cn(
            "flex items-center",
            isHorizontal ? "flex-1" : "flex-row gap-3",
          )}
        >
          {/* Step circle */}
          <div className="flex items-center gap-2">
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: index * 0.1 }}
              className={cn(
                "relative flex h-8 w-8 items-center justify-center rounded-full border-2 transition-colors",
                step.status === "completed" &&
                  "border-green-500 bg-green-500 text-white",
                step.status === "in_progress" &&
                  "border-primary/60 bg-primary/10 text-primary",
                step.status === "error" &&
                  "border-destructive bg-destructive text-white",
                step.status === "pending" &&
                  "border-muted-foreground/30 bg-muted text-muted-foreground",
              )}
            >
              {step.status === "completed" && (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 300, damping: 20 }}
                >
                  <Check className="h-4 w-4" />
                </motion.div>
              )}
              {step.status === "in_progress" && (
                <CircleDot className="h-4 w-4" />
              )}
              {step.status === "error" && <X className="h-4 w-4" />}
              {step.status === "pending" && (
                <Circle className="h-3 w-3 fill-current" />
              )}
            </motion.div>

            {/* Step label (for horizontal) */}
            {isHorizontal && (
              <span
                className={cn(
                  "text-sm font-medium whitespace-nowrap",
                  step.status === "completed" && "text-green-600",
                  step.status === "in_progress" && "text-primary",
                  step.status === "error" && "text-destructive",
                  step.status === "pending" && "text-muted-foreground",
                )}
              >
                {step.name}
              </span>
            )}
          </div>

          {/* Step label and message (for vertical) */}
          {!isHorizontal && (
            <div className="flex-1">
              <span
                className={cn(
                  "text-sm font-medium",
                  step.status === "completed" && "text-green-600",
                  step.status === "in_progress" && "text-primary",
                  step.status === "error" && "text-destructive",
                  step.status === "pending" && "text-muted-foreground",
                )}
              >
                {step.name}
              </span>
              {step.message && (
                <p className="text-muted-foreground mt-0.5 text-xs">
                  {step.message}
                </p>
              )}
            </div>
          )}

          {/* Connector line (for horizontal, except last) */}
          {isHorizontal && index < steps.length - 1 && (
            <div className="mx-2 flex-1">
              <div
                className={cn(
                  "h-0.5 w-full rounded-full transition-colors",
                  step.status === "completed"
                    ? "bg-green-500"
                    : "bg-muted-foreground/20",
                )}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

interface StepIndicatorCompactProps {
  steps: Step[];
  className?: string;
}

export function StepIndicatorCompact({
  steps,
  className,
}: StepIndicatorCompactProps) {
  const completedCount = steps.filter((s) => s.status === "completed").length;
  const currentStep = steps.find((s) => s.status === "in_progress");
  const hasError = steps.some((s) => s.status === "error");

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">
          {hasError
            ? "Error occurred"
            : currentStep
              ? currentStep.name
              : completedCount === steps.length
                ? "Complete"
                : "Ready"}
        </span>
        <span className="text-muted-foreground">
          {completedCount}/{steps.length}
        </span>
      </div>
      <div className="flex gap-1">
        {steps.map((step, index) => (
          <motion.div
            key={step.id}
            className={cn(
              "h-1.5 flex-1 rounded-full",
              step.status === "completed" && "bg-green-500",
              step.status === "in_progress" && "bg-primary",
              step.status === "error" && "bg-destructive",
              step.status === "pending" && "bg-muted",
            )}
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ delay: index * 0.05 }}
            style={{ originX: 0 }}
          />
        ))}
      </div>
    </div>
  );
}
