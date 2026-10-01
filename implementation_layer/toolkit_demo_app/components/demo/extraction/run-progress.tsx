"use client";

import { StepIndicator } from "@/components/demo/step-indicator";
import { Card, CardContent } from "@/components/ui/card";
import type { SSEStep } from "@/lib/sse";
import { Loader2 } from "lucide-react";

/** The real steps of the running pipeline, as the server reports them. */
export function RunProgress({ steps }: { steps: SSEStep[] }) {
  const current = steps.find((step) => step.status === "in_progress");
  return (
    <Card className="border-primary/20 shadow-md" aria-live="polite">
      <CardContent className="space-y-5 pt-6">
        <div className="flex items-center gap-4">
          <div className="bg-primary/10 flex size-12 items-center justify-center rounded-full">
            <Loader2 className="text-primary size-6 animate-spin" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">
              {current?.name ?? "Starting..."}
            </h3>
            {current?.message && (
              <p className="text-muted-foreground text-sm">{current.message}</p>
            )}
          </div>
        </div>
        {steps.length > 0 && (
          <div className="bg-muted/30 rounded-lg border p-4">
            <StepIndicator
              steps={steps.map((step) => ({
                id: String(step.step),
                name: step.name,
                status: step.status,
                message: step.message,
              }))}
              orientation="vertical"
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
