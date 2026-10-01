import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { FlaskConical, Mail, Rocket } from "lucide-react";

const CONTACT_EMAIL = "info@gaik.ai";

/** Highlights that every demo can be tried with your own data, and the free PoC offer. */
export function OwnDataCallout() {
  return (
    <section
      aria-label="Try with your own data"
      className="border-primary/40 bg-primary/10 grid gap-6 rounded-xl border-2 p-5 md:grid-cols-2"
    >
      <div className="flex gap-4">
        <span className="bg-primary text-primary-foreground flex size-11 shrink-0 items-center justify-center rounded-xl shadow-sm">
          <FlaskConical className="size-6" />
        </span>
        <div className="space-y-1.5">
          <h2 className="font-serif text-xl font-semibold text-balance md:text-2xl">
            Try it hands-on with your own data
          </h2>
          <p className="text-muted-foreground">
            Get a hands-on experience with the components and use cases of the
            GAIK GenAI toolkit using <strong>your own documents</strong>,
            recordings and data, right in your browser.
          </p>
        </div>
      </div>

      <div className="bg-card/80 flex flex-col justify-between gap-4 rounded-xl border p-5">
        <div className="flex gap-3">
          <Rocket className="text-primary mt-0.5 size-5 shrink-0" />
          <div className="space-y-1">
            <h3 className="font-semibold">Want to build your own PoC?</h3>
            <p className="text-muted-foreground text-sm">
              Companies in Finland can contact GAIK&apos;s team for{" "}
              <strong>free proof-of-concept development</strong>.
            </p>
          </div>
        </div>
        <a
          href={`mailto:${CONTACT_EMAIL}`}
          className={cn(buttonVariants(), "w-fit gap-2")}
        >
          <Mail className="size-4" />
          Contact GAIK&apos;s team: {CONTACT_EMAIL}
        </a>
      </div>
    </section>
  );
}
