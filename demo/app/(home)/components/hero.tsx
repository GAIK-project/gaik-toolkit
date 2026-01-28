"use client";

import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

export function Hero() {
  return (
    <section className="bg-card relative overflow-hidden rounded-3xl border p-8 shadow-sm md:p-12">
      <div className="space-y-6">
        <div className="space-y-3">
          <h1 className="max-w-3xl font-serif text-4xl font-semibold tracking-tight sm:text-5xl md:text-6xl">
            GAIK Toolkit Demos
          </h1>
          <p className="text-muted-foreground max-w-2xl text-lg">
            Interactive document AI demos. Parse, extract, classify, and
            transcribe with modern AI.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <Link
            href="/incident-report"
            className="bg-primary text-primary-foreground hover:bg-primary/90 inline-flex h-12 items-center justify-center gap-2 rounded-md px-6 text-base font-medium shadow-md transition-all"
          >
            Try Incident Report
            <ArrowRight className="ml-2 h-4 w-4" />
          </Link>
          <Button
            size="lg"
            variant="outline"
            className="h-12 px-6 text-base"
            onClick={() => {
              document
                .getElementById("demos")
                ?.scrollIntoView({ behavior: "smooth" });
            }}
          >
            Explore All Demos
          </Button>
        </div>
      </div>
    </section>
  );
}
