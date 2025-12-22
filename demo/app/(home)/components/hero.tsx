import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function Hero() {
  return (
    <section className="rounded-3xl border bg-card p-8 shadow-sm md:p-12">
      <div className="space-y-6">
        <Badge
          variant="secondary"
          className="w-fit uppercase tracking-[0.2em] text-[10px]"
        >
          GAIK Toolkit
        </Badge>
        <div className="space-y-3">
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl md:text-6xl font-serif">
            Interactive document AI demos.
          </h1>
          <p className="text-lg text-muted-foreground">
            Parse, extract, classify, and transcribe in minutes.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button size="lg" asChild>
            <Link href="/pipeline">
              Launch Pipeline
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button size="lg" variant="outline" asChild>
            <a
              href="https://pypi.org/project/gaik/"
              target="_blank"
              rel="noopener noreferrer"
            >
              PyPI Package
            </a>
          </Button>
        </div>
      </div>
    </section>
  );
}
