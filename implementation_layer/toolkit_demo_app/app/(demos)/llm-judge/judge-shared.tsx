"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { RateLimitError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { AlertTriangle, Check, CheckCircle2, X, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import type { Severity } from "./judge-data";

export interface Usage {
  provider?: string | null;
  model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  duration_s?: number | null;
  cost_usd?: number | null;
}

const SEVERITY_BADGE: Record<
  Severity,
  { className: string; icon: typeof CheckCircle2 }
> = {
  ok: {
    className: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30",
    icon: CheckCircle2,
  },
  suspect: {
    className: "bg-amber-500/10 text-amber-700 border-amber-500/30",
    icon: AlertTriangle,
  },
  wrong: {
    className: "bg-rose-500/10 text-rose-700 border-rose-500/30",
    icon: XCircle,
  },
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  const { className, icon: Icon } = SEVERITY_BADGE[severity];
  return (
    <Badge variant="outline" className={cn("gap-1", className)}>
      <Icon className="h-3 w-3" />
      {severity}
    </Badge>
  );
}

const SCORE_COLOUR = [
  "",
  "bg-rose-500",
  "bg-amber-500",
  "bg-amber-400",
  "bg-emerald-400",
  "bg-emerald-500",
];

/** The score from 1 to 5 as five blocks, filled up to the score. */
export function ScoreMeter({ score }: { score: number | undefined }) {
  if (score === undefined || score <= 0) return null;
  const rounded = Math.min(5, Math.max(1, Math.round(score)));
  return (
    <span
      className="inline-flex items-center gap-1"
      role="meter"
      aria-valuenow={rounded}
      aria-valuemin={1}
      aria-valuemax={5}
      aria-label={`Score ${rounded} of 5`}
    >
      <span className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map((step) => (
          <span
            key={step}
            className={cn(
              "h-3 w-3 rounded-sm",
              step <= rounded ? SCORE_COLOUR[rounded] : "bg-muted",
            )}
          />
        ))}
      </span>
      <span className="font-mono text-xs">{rounded}/5</span>
    </span>
  );
}

/** Whether a verdict is what the example expected. */
export function ExpectationLine({
  met,
  expectedText,
  detail,
}: {
  met: boolean;
  expectedText: string;
  detail?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-xs",
        met
          ? "border-emerald-500/30 bg-emerald-500/5"
          : "border-amber-500/40 bg-amber-500/5",
      )}
    >
      {met ? (
        <Check className="size-4 text-emerald-600" />
      ) : (
        <X className="size-4 text-amber-600" />
      )}
      <span className="font-medium">
        {met ? "As expected" : "Not what was expected"}
      </span>
      <span className="text-muted-foreground">{expectedText}</span>
      {detail && <span>{detail}</span>}
    </div>
  );
}

export function UsageBar({ usage }: { usage: Usage | null | undefined }) {
  if (!usage) return null;
  const items: { label: string; value: string }[] = [];
  if (usage.provider || usage.model) {
    items.push({
      label: "Model",
      value: `${usage.provider ?? ""}${usage.provider && usage.model ? " · " : ""}${usage.model ?? ""}`,
    });
  }
  if (usage.total_tokens != null)
    items.push({ label: "Tokens", value: usage.total_tokens.toLocaleString() });
  if (usage.duration_s != null)
    items.push({ label: "Duration", value: `${usage.duration_s.toFixed(2)}s` });
  if (usage.cost_usd != null)
    items.push({ label: "Cost", value: `$${usage.cost_usd.toFixed(4)}` });
  if (items.length === 0) return null;
  return (
    <div className="bg-muted/40 grid grid-cols-2 gap-2 rounded-md border p-3 text-xs sm:grid-cols-4">
      {items.map((stat) => (
        <div key={stat.label}>
          <p className="text-muted-foreground">{stat.label}</p>
          <p className="font-mono break-all">{stat.value}</p>
        </div>
      ))}
    </div>
  );
}

export function RawJson({
  data,
  label = "Raw judge response",
}: {
  data: unknown;
  label?: string;
}) {
  return (
    <Accordion type="single" collapsible className="w-full">
      <AccordionItem value="raw" className="border-none">
        <AccordionTrigger className="text-muted-foreground hover:text-foreground py-2 text-xs font-medium">
          {label}
        </AccordionTrigger>
        <AccordionContent>
          <pre className="bg-muted max-h-72 overflow-auto rounded p-3 text-xs">
            <code>{JSON.stringify(data, null, 2)}</code>
          </pre>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}

/** How the 1 to 5 score reads: 1 wrong, 2 to 3 suspect, 4 to 5 ok. */
export function ScoringGuide() {
  const rows: { score: string; severity: Severity; label: string }[] = [
    { score: "1", severity: "wrong", label: "Clearly wrong" },
    {
      score: "2–3",
      severity: "suspect",
      label: "Suspect: review before accepting",
    },
    { score: "4–5", severity: "ok", label: "Looks correct" },
  ];
  return (
    <div className="bg-muted/40 rounded-md border p-3 text-xs">
      <p className="text-muted-foreground mb-2 font-medium">
        How the score reads (Likert 1–5):
      </p>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {rows.map((row) => (
          <div key={row.score} className="flex items-center gap-1.5">
            <Badge variant="secondary" className="font-mono">
              {row.score}
            </Badge>
            <SeverityBadge severity={row.severity} />
            <span className="text-muted-foreground">{row.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** One ready-made case to pick, with what it shows. */
export function ExampleCard({
  title,
  summary,
  tag,
  selected,
  disabled,
  onClick,
}: {
  title: string;
  summary: string;
  tag?: string;
  selected: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex flex-col gap-1 rounded-xl border-2 p-3 text-left transition-all",
        selected
          ? "border-primary bg-primary/5"
          : "bg-card hover:border-primary/40",
      )}
    >
      <span className="text-sm font-semibold">{title}</span>
      <span className="text-muted-foreground text-xs">{summary}</span>
      {tag && (
        <span>
          <Badge variant="outline" className="font-normal">
            {tag}
          </Badge>
        </span>
      )}
    </button>
  );
}

// Shared submit plumbing for the modes: owns the abort controller, isLoading, result state,
// and the standard AbortError / RateLimitError swallow. Each mode keeps its own validation
// and request body in the `executor`.
export function useJudgeSubmit<T>() {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<T | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function run(executor: (signal: AbortSignal) => Promise<T>) {
    if (isLoading) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setIsLoading(true);
    setResult(null);
    try {
      setResult(await executor(abortRef.current.signal));
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      if (e instanceof RateLimitError) return;
      toast.error(e instanceof Error ? e.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  return { isLoading, result, setResult, run };
}

/** The message of a response that is not ok, with a fallback. */
export async function readJudgeError(
  response: Response,
  fallback: string,
): Promise<string> {
  const err = await response.json().catch(() => null);
  const detail = err?.detail;
  if (typeof detail === "string") return detail;
  if (typeof detail?.message === "string") return detail.message;
  return fallback;
}
