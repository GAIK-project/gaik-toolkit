"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { buttonVariants } from "@/components/ui/button";
import { ArrowRight, BookOpen, Wand2 } from "lucide-react";

// The Solution Configuration Wizard is not run in this demo. Wizard V2 is its own
// service, where each session's agent and its PoC runs are kept apart from other
// services, and it needs an account from the GAIK team. The first version is a
// Claude Code skill that runs on the person's own computer.
const CLASSIC_WIZARD_DOCS =
  "https://gaik-project.github.io/gaik-toolkit/guidance-layer/solution-configuration-wizard/";

export function SolutionWizardNotice({
  wizardUrl,
}: {
  wizardUrl: string | null;
}) {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <DemoPageHeader
        icon={Wand2}
        iconClassName="h-8 w-8 text-primary"
        title="Solution Configuration Wizard"
        description="From a use case description to a blueprint, a runnable PoC and its documentation"
      />
      <section className="border-primary/40 bg-muted/40 space-y-4 rounded-lg border p-5">
        <h2 className="text-lg font-semibold">Wizard V2 (recommended)</h2>
        <p>
          The wizard runs as its own service. Sign in with an account from the
          GAIK team; if you do not have one, ask the team for it.
        </p>
        {wizardUrl ? (
          <a
            href={wizardUrl}
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
      <section className="border-border space-y-4 rounded-lg border p-5">
        <h2 className="text-lg font-semibold">The first wizard in Claude Code</h2>
        <p>
          The first version of the wizard is a Claude Code skill. It runs on
          your own computer with your own Claude account and needs no GAIK
          account.
        </p>
        <a
          href={CLASSIC_WIZARD_DOCS}
          className={buttonVariants({ variant: "outline", className: "gap-2" })}
          rel="noopener"
        >
          How to run it
          <BookOpen className="size-4" />
        </a>
      </section>
    </div>
  );
}
