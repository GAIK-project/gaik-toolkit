"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { buttonVariants } from "@/components/ui/button";
import { ArrowRight, Wand2 } from "lucide-react";

// The Solution Configuration Wizard runs as its own service (Wizard V2), where
// each session's agent and its PoC runs are kept apart from other services. This
// demo no longer runs it; the page says where it is.
const WIZARD_URL = process.env.NEXT_PUBLIC_WIZARD_V2_URL;

export default function SolutionWizardPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <DemoPageHeader
        icon={Wand2}
        iconClassName="h-8 w-8 text-primary"
        title="Solution Configuration Wizard"
        description="From a use case description to a blueprint, a runnable PoC and its documentation"
      />
      <section className="border-border bg-muted/40 space-y-4 rounded-lg border p-5">
        <p>
          The wizard has moved to its own service, <strong>Wizard V2</strong>.
          It is not run in this demo any more.
        </p>
        {WIZARD_URL ? (
          <a
            href={WIZARD_URL}
            className={buttonVariants({ className: "gap-2" })}
            rel="noopener"
          >
            Open Wizard V2
            <ArrowRight className="size-4" />
          </a>
        ) : (
          <p className="text-muted-foreground text-sm">
            Ask the GAIK team for access to Wizard V2.
          </p>
        )}
      </section>
    </div>
  );
}
