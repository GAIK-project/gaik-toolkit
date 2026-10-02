"use client";

import { Button, buttonVariants } from "@/components/ui/button";
import { PageTransition } from "@/components/demo/page-transition";
import { cn } from "@/lib/utils";
import { ArrowRight, Wand2 } from "lucide-react";
import Link from "next/link";
import { OwnDataCallout } from "./own-data-callout";
import { ProcessOverview } from "./process-overview";
import { WizardEntry } from "./wizard-entry";

export function Hero({
  hasWizardAccess,
  isAuthenticated,
}: {
  hasWizardAccess: boolean;
  isAuthenticated: boolean;
}) {
  function scrollToDemos(): void {
    document.getElementById("demos")?.scrollIntoView({ behavior: "smooth" });
  }

  const wizardClassName =
    "text-primary group inline-flex w-fit max-w-full items-center gap-2 text-left text-sm font-medium";
  const wizardContent = (
    <>
      <Wand2 className="size-4 shrink-0" />
      <span className="underline underline-offset-4">
        Solution Configuration Wizard (beta)
      </span>
      <ArrowRight className="size-4 shrink-0 transition-transform group-hover:translate-x-0.5" />
    </>
  );

  const newLinkClassName =
    "text-primary font-medium underline underline-offset-4 hover:text-primary/80 transition-colors";

  return (
    <PageTransition className="bg-card relative overflow-hidden rounded-2xl border p-6 shadow-sm md:p-10">
      {/* A soft wash of the site colour behind the overview. */}
      <div
        aria-hidden
        className="bg-primary/10 pointer-events-none absolute -top-32 -right-32 hidden size-[28rem] rounded-full blur-3xl lg:block"
      />
      <div className="relative space-y-6">
        <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,1fr)_21rem]">
          <div className="space-y-6">
            <div className="space-y-4" data-tour="hero">
              <h1 className="max-w-3xl font-serif text-4xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-[2.75rem]">
                Generative AI building blocks for knowledge work
              </h1>
              <p className="text-muted-foreground max-w-2xl text-base md:text-lg">
                Capture knowledge from documents and recordings, find answers in
                it, and write source-grounded reports. Every component, module
                and use case runs in your browser.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <Link
                href="/luvata-order"
                className={cn(
                  buttonVariants({ size: "lg" }),
                  "h-11 gap-2 px-5 shadow-sm",
                )}
              >
                Try Purchase Order Processing
                <ArrowRight className="size-4" />
              </Link>
              <Button
                size="lg"
                variant="outline"
                className="h-11 px-5"
                onClick={scrollToDemos}
              >
                Explore all demos
              </Button>
            </div>

            {/* Solution Configuration Wizard — beta. */}
            <div className="flex flex-col gap-2.5">
              <WizardEntry
                hasWizardAccess={hasWizardAccess}
                isAuthenticated={isAuthenticated}
                tour="wizard"
                className={wizardClassName}
              >
                {wizardContent}
              </WizardEntry>

              {/* Update: what is new. Edit the text here; link only to pages that exist. */}
              <p data-tour="update" className="text-muted-foreground text-sm">
                <span className="text-foreground font-medium">New:</span>{" "}
                <Link href="/report-writer-v2" className={newLinkClassName}>
                  Report Writer
                </Link>
                ,{" "}
                <Link href="/source-normalizer" className={newLinkClassName}>
                  Source Normalizer
                </Link>
                ,{" "}
                <Link href="/knowledge-curator" className={newLinkClassName}>
                  Knowledge Curator
                </Link>{" "}
                and{" "}
                <Link href="/knowledge-synthesis" className={newLinkClassName}>
                  Knowledge Synthesizer
                </Link>
              </p>
            </div>
          </div>

          <ProcessOverview className="hidden lg:flex" />
        </div>

        <OwnDataCallout />
      </div>
    </PageTransition>
  );
}
