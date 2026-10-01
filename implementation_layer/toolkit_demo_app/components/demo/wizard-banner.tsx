import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ArrowRight, Wand2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

/**
 * An image of the use case, under a highlighted way on to the Solution Configuration
 * Wizard. `useCase` completes "Want to build your own ... use case?".
 */
export function WizardBanner({
  useCase,
  image,
  imageAlt,
  imagePosition = "center",
}: {
  useCase: string;
  image: string;
  imageAlt: string;
  imagePosition?: string;
}) {
  return (
    <section
      aria-label={`Build your own ${useCase} use case`}
      className="border-primary/40 overflow-hidden rounded-2xl border-2 shadow-sm"
    >
      <div className="from-primary/15 via-card to-card flex flex-col gap-4 bg-gradient-to-br p-5 md:flex-row md:items-center md:justify-between md:p-6">
        <div className="flex gap-4">
          <span className="bg-primary text-primary-foreground flex size-11 shrink-0 items-center justify-center rounded-xl shadow-sm">
            <Wand2 className="size-6" />
          </span>
          <div className="space-y-1">
            <h2 className="font-serif text-xl font-semibold text-balance md:text-2xl">
              Want to build your own {useCase} use case?
            </h2>
            <p className="text-muted-foreground">
              Go to the <strong>Solution Configuration Wizard</strong> to build
              your complete solution (PoC), with deployable code and
              documentation.
            </p>
          </div>
        </div>
        <Link
          href="/solution-wizard"
          className={cn(buttonVariants({ size: "lg" }), "shrink-0 gap-2")}
        >
          Open the Solution Wizard
          <ArrowRight className="size-4" />
        </Link>
      </div>
      <div className="relative h-56 sm:h-72 lg:h-80">
        <Image
          src={image}
          alt={imageAlt}
          fill
          sizes="(min-width: 1280px) 1200px, 100vw"
          className="object-cover"
          style={{ objectPosition: imagePosition }}
        />
      </div>
    </section>
  );
}
