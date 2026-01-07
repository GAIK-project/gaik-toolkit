"use client";

import { Step, StepIndicator } from "@/components/demo/step-indicator";
import { cn } from "@/lib/utils";

interface DemoStepperProps {
  steps: Step[];
  className?: string;
}

export function DemoStepper({ steps, className }: DemoStepperProps) {
  return (
    <div className={cn("bg-card rounded-2xl border p-4 shadow-sm", className)}>
      <StepIndicator steps={steps} orientation="horizontal" />
    </div>
  );
}
