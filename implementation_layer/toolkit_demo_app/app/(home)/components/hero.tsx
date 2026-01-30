"use client";

import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

export function Hero() {
  function scrollToDemos(): void {
    document.getElementById("demos")?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <section className="animate-in fade-in duration-500 bg-card relative overflow-hidden rounded-3xl border p-8 shadow-sm md:p-12">
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
          <Button asChild size="lg" className="h-12 gap-2 px-6 text-base shadow-md">
            <Link href="/incident-report">
              Interactive Demo
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button
            size="lg"
            variant="outline"
            className="h-12 px-6 text-base"
            onClick={scrollToDemos}
          >
            Explore All Demos
          </Button>
        </div>
      </div>
    </section>
  );
}
