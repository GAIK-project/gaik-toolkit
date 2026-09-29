"use client";

import { useOnboarding } from "@/components/onboarding/onboarding-provider";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageTransition } from "@/components/demo/page-transition";
import { cn } from "@/lib/utils";
import { ArrowRight, Sparkles, Wand2 } from "lucide-react";
import Link from "next/link";

export function Hero({
  hasWizardAccess,
  isAuthenticated,
}: {
  hasWizardAccess: boolean;
  isAuthenticated: boolean;
}) {
  const { openWizardAccess } = useOnboarding();

  function scrollToDemos(): void {
    document.getElementById("demos")?.scrollIntoView({ behavior: "smooth" });
  }

  // Access holders go straight in. Anonymous visitors follow the same sign-in
  // path as the other demos; signed-in users without the grant get the beta
  // access dialog.
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

  const updateLinkClassName =
    "font-semibold whitespace-nowrap text-amber-900 underline underline-offset-2 transition-colors hover:text-amber-700";

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

        {/* Update: what is new. Edit the text here; link only to pages that exist. */}
        <div
          data-tour="update"
          className="flex w-fit max-w-full flex-col gap-2 rounded-2xl border border-amber-300/80 bg-amber-50/70 px-4 py-3 sm:flex-row sm:items-center sm:gap-3"
        >
          <span className="flex w-fit shrink-0 items-center gap-1.5 rounded-full bg-amber-500 px-2.5 py-0.5 text-[11px] font-bold tracking-wider text-white uppercase">
            <Sparkles className="size-3" />
            Update
          </span>
          <p className="text-sm text-slate-700">
            The{" "}
            <Link href="/report-writer-v2" className={updateLinkClassName}>
              Report Writer
            </Link>{" "}
            module is now available. Its stages also work as separate
            components:{" "}
            <Link href="/source-normalizer" className={updateLinkClassName}>
              source normalization
            </Link>
            ,{" "}
            <Link href="/knowledge-curator" className={updateLinkClassName}>
              knowledge curation
            </Link>{" "}
            and{" "}
            <Link href="/knowledge-synthesis" className={updateLinkClassName}>
              knowledge synthesis
            </Link>
            .
          </p>
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
        ) : !isAuthenticated ? (
          <Link href="/sign-in" data-tour="wizard" className={pillClassName}>
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
