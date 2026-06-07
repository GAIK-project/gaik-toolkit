"use client";

import { Button, buttonVariants } from "@/components/ui/button";
import { PageTransition } from "@/components/demo/page-transition";
import { cn } from "@/lib/utils";
import { ArrowRight, Sparkles, Wand2 } from "lucide-react";
import Link from "next/link";

export function Hero() {
  function scrollToDemos(): void {
    document.getElementById("demos")?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <PageTransition
      className="bg-card relative overflow-hidden rounded-3xl border p-8 shadow-sm md:p-12"
    >
      <div className="space-y-6">
        <div className="space-y-3">
          <h1 className="max-w-3xl font-serif text-4xl font-semibold tracking-tight sm:text-5xl md:text-6xl">
            GAIK Toolkit Demos
          </h1>
          <p className="text-muted-foreground max-w-2xl text-lg">
            Interactive demos of GAIK toolkit's software components, software
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

        {/* Solution Configuration Wizard — new feature callout */}
        <Link
          href="/solution-wizard"
          className="group relative flex w-full items-center gap-4 overflow-hidden rounded-2xl border border-teal-200 bg-gradient-to-r from-teal-50 to-cyan-50 px-6 py-5 shadow-sm transition-all hover:border-teal-300 hover:shadow-md"
        >
          {/* subtle glow */}
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_left,_rgba(20,184,166,0.08)_0%,_transparent_60%)]" />

          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-600/10">
            <Wand2 className="size-5 text-teal-600" />
          </div>

          <div className="min-w-0 flex-1 space-y-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-base font-bold text-teal-700">
                Solution Configuration Wizard
              </span>
              <span className="animate-pulse inline-flex items-center gap-1 rounded-full bg-red-500 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                <Sparkles className="size-2.5" />
                New
              </span>
            </div>
            <p className="text-sm leading-snug text-slate-600">
              Describe your use case — the wizard collects requirements and
              creates a working, validated, proof of concept with documentation,
              diagrams, and all necessary artifacts.
            </p>
          </div>

          <ArrowRight className="ml-4 shrink-0 text-teal-400 transition-all group-hover:translate-x-1 group-hover:text-teal-600" />
        </Link>
      </div>
    </PageTransition>
  );
}
