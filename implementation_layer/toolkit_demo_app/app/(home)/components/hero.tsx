"use client";

import { useOnboarding } from "@/components/onboarding/onboarding-provider";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageTransition } from "@/components/demo/page-transition";
import { cn } from "@/lib/utils";
import { ArrowRight, Wand2 } from "lucide-react";
import Link from "next/link";

export function Hero({ hasWizardAccess }: { hasWizardAccess: boolean }) {
  const { openWizardAccess } = useOnboarding();

  function scrollToDemos(): void {
    document.getElementById("demos")?.scrollIntoView({ behavior: "smooth" });
  }

  // Visitors who can already open the Wizard go straight there; everyone else
  // gets the "how to request beta access" dialog.
  const pillClassName =
    "group flex w-fit max-w-full items-center gap-3 rounded-full border border-teal-200/80 bg-teal-50/60 py-2 pr-3 pl-2.5 text-left transition-colors hover:border-teal-300 hover:bg-teal-50";
  const pillContent = (
    <>
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-teal-600/10">
        <Wand2 className="size-3.5 text-teal-700" />
      </span>
      <span className="min-w-0 truncate text-sm text-slate-700">
        <span className="font-semibold text-teal-800">
          Solution Configuration Wizard
        </span>
        <span className="text-muted-foreground hidden sm:inline">
          {" "}
          turns a plain-language use case into a validated proof of concept.
        </span>
      </span>
      <span className="shrink-0 rounded-full bg-teal-600/15 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-teal-800 uppercase">
        Beta
      </span>
      <ArrowRight className="size-3.5 shrink-0 text-teal-700 transition-transform group-hover:translate-x-0.5" />
    </>
  );

  return (
    <PageTransition className="bg-card relative overflow-hidden rounded-3xl border p-8 shadow-sm md:p-12">
      <div className="space-y-6">
        <div className="space-y-3" data-tour="hero">
          <h1 className="max-w-3xl font-serif text-4xl font-semibold tracking-tight sm:text-5xl md:text-6xl">
            GAIK Toolkit Demos
          </h1>
          <p className="text-muted-foreground max-w-2xl text-lg">
            Interactive demos of GAIK toolkit&apos;s software components, software
            modules, and general use cases.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <Link
            href="/incident-report"
            className={cn(
              buttonVariants({ size: "lg" }),
              "h-12 gap-2 px-6 text-base shadow-md",
            )}
          >
            Interactive Demo
            <ArrowRight className="size-4" />
          </Link>
          <Button
            size="lg"
            variant="outline"
            className="h-12 px-6 text-base"
            onClick={scrollToDemos}
          >
            Explore All Demos
          </Button>
        </div>

        {/* Solution Configuration Wizard — beta. Access holders go straight in;
            others get the access-request dialog. */}
        {hasWizardAccess ? (
          <Link
            href="/solution-wizard"
            data-tour="wizard"
            className={pillClassName}
          >
            {pillContent}
          </Link>
        ) : (
          <button
            type="button"
            data-tour="wizard"
            onClick={openWizardAccess}
            className={pillClassName}
          >
            {pillContent}
          </button>
        )}
      </div>
    </PageTransition>
  );
}
