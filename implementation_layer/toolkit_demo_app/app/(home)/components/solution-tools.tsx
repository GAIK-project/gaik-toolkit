import { EuFlag } from "@/components/eu-flag";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ArrowRight, Lock, Wand2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

/**
 * The two tools that are not demos of a component: the Solution Configuration
 * Wizard (this page's one way on to it) and the EU AI Act screening. They sit
 * under the hero, so both are on the first screen. The screening runs a model, so
 * like the demo cards it sends a visitor who cannot run it to sign in first.
 */
export function SolutionTools({ canRunDemos }: { canRunDemos: boolean }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section
        aria-labelledby="wizard-heading"
        data-tour="wizard"
        className="border-primary/40 from-primary/15 via-card to-card grid overflow-hidden rounded-2xl border-2 bg-gradient-to-br shadow-sm sm:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)] lg:col-span-2"
      >
        <div className="flex flex-col gap-4 p-5 md:p-6">
          <span className="bg-primary text-primary-foreground flex size-11 shrink-0 items-center justify-center rounded-xl shadow-sm">
            <Wand2 className="size-6" />
          </span>
          <div className="space-y-1.5">
            <h2
              id="wizard-heading"
              className="font-serif text-xl font-semibold text-balance md:text-2xl"
            >
              Solution Configuration Wizard
            </h2>
            <p className="text-muted-foreground">
              Describe a business problem in plain words. The wizard picks the
              GAIK components and builds a blueprint, a runnable proof of
              concept and its documentation.
            </p>
          </div>
          <Link
            href="/solution-wizard"
            className={cn(
              buttonVariants({ size: "lg" }),
              "mt-auto w-fit gap-2 shadow-sm",
            )}
          >
            Open the Solution Wizard
            <ArrowRight className="size-4" />
          </Link>
        </div>
        {/* Wizard V2's own screen, cropped to its gates and process steps. */}
        <div className="relative h-44 pl-5 sm:h-auto sm:pt-6 sm:pl-0">
          <div className="bg-background relative h-full overflow-hidden rounded-tl-xl border-t border-l shadow-[0_-12px_40px_-20px_rgb(15_23_42/0.25)]">
            <Image
              src="/solution-wizard/wizard-v2.webp"
              alt="Wizard V2: its four gates along the top and the use case's process steps below them."
              fill
              sizes="(min-width: 1024px) 360px, (min-width: 640px) 45vw, 100vw"
              className="object-cover object-left-top"
            />
          </div>
        </div>
      </section>

      <section
        aria-labelledby="ai-act-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 shadow-sm md:p-6"
      >
        <span className="bg-primary/10 flex size-11 shrink-0 items-center justify-center rounded-xl">
          <EuFlag />
        </span>
        <div className="space-y-1.5">
          <h2
            id="ai-act-heading"
            className="font-serif text-xl font-semibold text-balance md:text-2xl"
          >
            EU AI Act screening
          </h2>
          <p className="text-muted-foreground">
            Describe an AI use case, planned or already in use. Get its
            preliminary risk class and what you must do, and by when.
          </p>
        </div>
        <Link
          href={canRunDemos ? "/ai-act-screening" : "/sign-in"}
          title={canRunDemos ? undefined : "Sign in to open"}
          className={cn(
            buttonVariants({ variant: "outline", size: "lg" }),
            "mt-auto w-fit gap-2",
          )}
        >
          Screen a use case
          {canRunDemos ? (
            <ArrowRight className="size-4" />
          ) : (
            <Lock className="size-4" />
          )}
        </Link>
      </section>
    </div>
  );
}
