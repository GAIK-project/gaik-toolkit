import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Hero() {
  return (
    <section className="bg-card rounded-3xl border p-8 shadow-sm md:p-12">
      <div className="space-y-6">
        <div className="space-y-3">
          <h1 className="font-serif text-4xl font-semibold tracking-tight sm:text-5xl md:text-6xl">
            Interactive document AI demos.
          </h1>
          <p className="text-muted-foreground text-lg">
            Parse, extract, classify, and transcribe in minutes.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button size="lg" asChild>
            <Link href="/incident-report">
              Try Incident Report
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button size="lg" variant="outline" asChild>
            <a href="#demos">See All Demos</a>
          </Button>
        </div>
      </div>
    </section>
  );
}
