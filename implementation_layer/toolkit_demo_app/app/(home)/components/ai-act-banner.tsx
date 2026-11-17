import { cn } from "@/lib/utils";
import { ArrowRight, ShieldCheck } from "lucide-react";
import Link from "next/link";

/** The entry to the EU AI Act screening demo, above the knowledge processes in the hero. */
export function AiActBanner({ className }: { className?: string }) {
  return (
    <Link
      href="/ai-act-screening"
      data-testid="ai-act-banner"
      className={cn(
        "bg-primary/10 border-primary/40 group flex items-center gap-4 rounded-xl border-2 p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md motion-reduce:hover:translate-y-0",
        className,
      )}
    >
      <span className="bg-primary text-primary-foreground flex size-12 shrink-0 items-center justify-center rounded-xl shadow-sm">
        <ShieldCheck className="size-6" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="text-primary block text-base font-semibold">
          EU AI Act screening
        </span>
        <span className="text-muted-foreground block text-sm">
          Screen your AI idea, pilot or product for AI Act compliance
        </span>
      </span>
      <ArrowRight className="text-primary size-5 shrink-0 transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}
