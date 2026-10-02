"use client";

import { Button, buttonVariants } from "@/components/ui/button";
import { PageTransition } from "@/components/demo/page-transition";
import { cn } from "@/lib/utils";
import { ArrowRight, Sparkles, Wand2 } from "lucide-react";
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

  const pillClassName =
    "group flex w-fit max-w-full items-center gap-3 rounded-3xl border border-teal-200/80 bg-teal-50/60 py-2 pr-3 pl-2.5 text-left transition-colors hover:border-teal-300 hover:bg-teal-50";
  const pillContent = (
    <>
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-teal-600/10">
        <Wand2 className="size-3.5 text-teal-700" />
      </span>
      <span className="min-w-0 text-sm text-slate-700">
        <span className="font-semibold text-teal-800">
          Solution Configuration Wizard
        </span>
        <span className="text-muted-foreground hidden sm:inline">
          {" "}
          designs a proof of concept for you.
        </span>
      </span>
      <span className="shrink-0 rounded-full bg-teal-600/15 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-teal-800 uppercase">
        Beta
      </span>
      <ArrowRight className="size-3.5 shrink-0 text-teal-700 transition-transform group-hover:translate-x-0.5" />
    </>
  );

  const newLinkClassName =
    "bg-primary/10 text-primary hover:bg-primary/20 rounded-md px-1.5 py-0.5 font-semibold underline underline-offset-2 transition-colors";

  return (
    <PageTransition className="bg-card relative overflow-hidden rounded-2xl border p-6 shadow-sm md:p-10">
      {/* A soft wash of the site colour behind the overview. */}
      <div
        aria-hidden
        className="bg-primary/10 pointer-events-none absolute -top-32 -right-32 hidden size-[28rem] rounded-full blur-3xl lg:block"
      />
      <div className="relative space-y-6">
        {/* Update: what is new. Edit the text here; link only to pages that exist. */}
        <div
          data-tour="update"
          className="bg-background/70 flex w-fit max-w-full flex-wrap items-center gap-x-2 gap-y-1 rounded-2xl border py-1 pr-3 pl-1 text-sm sm:rounded-full"
        >
          <span className="bg-primary text-primary-foreground flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wider uppercase">
            <Sparkles className="size-3" />
            New
          </span>
          <Link href="/report-writer-v2" className={newLinkClassName}>
            Report Writer
          </Link>
          <span className="text-muted-foreground">with its stages:</span>
          <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
            <Link href="/source-normalizer" className={newLinkClassName}>
              Source Normalizer
            </Link>
            <span className="text-muted-foreground">·</span>
            <Link href="/knowledge-curator" className={newLinkClassName}>
              Knowledge Curator
            </Link>
            <span className="text-muted-foreground">·</span>
            <Link href="/knowledge-synthesis" className={newLinkClassName}>
              Knowledge Synthesizer
            </Link>
          </span>
        </div>

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
            <WizardEntry
              hasWizardAccess={hasWizardAccess}
              isAuthenticated={isAuthenticated}
              tour="wizard"
              className={pillClassName}
            >
              {pillContent}
            </WizardEntry>
          </div>

          <ProcessOverview className="hidden lg:flex" />
        </div>

        <OwnDataCallout />
      </div>
    </PageTransition>
  );
}
