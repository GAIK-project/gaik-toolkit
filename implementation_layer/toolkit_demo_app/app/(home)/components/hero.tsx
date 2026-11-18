import { buttonVariants } from "@/components/ui/button";
import { PageTransition } from "@/components/demo/page-transition";
import { cn } from "@/lib/utils";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { ProcessOverview } from "./process-overview";

/** The title, the lede and one demo to try; the knowledge processes beside them. */
export function Hero({ isAuthenticated }: { isAuthenticated: boolean }) {
  return (
    <PageTransition className="bg-card rounded-2xl border p-6 shadow-sm md:p-10">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_26rem] lg:gap-10">
        <div className="space-y-6">
          <div className="space-y-4" data-tour="hero">
            <h1 className="max-w-3xl font-serif text-4xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-[2.75rem]">
              Generative AI building blocks for knowledge work
            </h1>
            <p className="text-muted-foreground max-w-2xl text-base md:text-lg">
              Capture knowledge from documents and recordings, find answers in
              it, and write source-grounded reports. Every component, module and
              use case runs in your browser.
            </p>
          </div>

          <Link
            href="/luvata-order"
            className={cn(
              buttonVariants({ size: "lg" }),
              "h-11 gap-2 px-5 shadow-sm",
            )}
          >
            Try purchase order processing
            <ArrowRight className="size-4" />
          </Link>

          {!isAuthenticated && (
            <p className="text-muted-foreground text-sm">
              <Link href="/sign-in" className="text-primary hover:underline">
                Sign in
              </Link>{" "}
              or{" "}
              <Link href="/sign-up" className="text-primary hover:underline">
                create an account
              </Link>{" "}
              to run the demos.
            </p>
          )}
        </div>

        <ProcessOverview />
      </div>
    </PageTransition>
  );
}
