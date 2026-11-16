"use client";

import { motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * The five stages a wizard run moves through, in order. These are the
 * user-facing names for SKILL.md's internal phases (requirement rounds →
 * spec → schema/components/blueprint → PoC scaffold + validation → docs).
 */
export const WIZARD_STAGES = [
  { id: "requirements", label: "Requirements" },
  { id: "specification", label: "Specification" },
  { id: "blueprint", label: "Blueprint" },
  { id: "poc", label: "Proof of concept" },
  { id: "docs", label: "Documentation" },
] as const;

/**
 * Which stage the run has reached, derived from the artifacts on disk rather
 * than from parsing chat text. Files are ground truth: the wizard writes them
 * in phase order, and the file list is already polled for the file browser.
 *
 * Returns an index into {@link WIZARD_STAGES}; 0 when nothing has been written
 * yet (the run is still collecting requirements).
 */
export function deriveWizardStage(files: string[]): number {
  const has = (test: (f: string) => boolean) => files.some(test);
  const named = (...names: string[]) =>
    has((f) => names.includes(f.split("/").pop() ?? ""));

  if (named("user_guide.md", "developer_guide.md", "genai_product_canvas.md")) return 4;
  if (has((f) => f.startsWith("poc/")) || named("run_poc.py", "output_schema.py")) return 3;
  if (named("blueprint.json", "workflow.mmd", "workflow.bpmn")) return 2;
  if (named("technical_specification.md", "extraction_requirements.md", "evaluation_plan.md"))
    return 1;
  return 0;
}

/**
 * A restrained progress rail above the conversation. It answers one question
 * the chat cannot: "how far through this am I, and what comes next?" — which
 * the wizard previously only signalled with "Round 1" buried in prose.
 */
export function WizardProgress({
  stage,
  className,
}: {
  stage: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const pct = ((stage + 1) / WIZARD_STAGES.length) * 100;

  return (
    <div className={cn("select-none", className)}>
      <div
        className="bg-muted relative h-1 w-full overflow-hidden rounded-full"
        role="progressbar"
        aria-valuemin={1}
        aria-valuemax={WIZARD_STAGES.length}
        aria-valuenow={stage + 1}
        aria-label={`Wizard progress: ${WIZARD_STAGES[stage]?.label}`}
      >
        <motion.div
          className="bg-primary absolute inset-y-0 left-0 rounded-full"
          initial={false}
          animate={{ width: `${pct}%` }}
          transition={reduce ? { duration: 0 } : { duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>

      <ol className="text-muted-foreground mt-1.5 flex justify-between text-[11px]">
        {WIZARD_STAGES.map((s, i) => (
          <li
            key={s.id}
            aria-current={i === stage ? "step" : undefined}
            className={cn(
              "transition-colors",
              i < stage && "text-foreground/60",
              i === stage && "text-foreground font-medium",
            )}
          >
            {s.label}
          </li>
        ))}
      </ol>
    </div>
  );
}
