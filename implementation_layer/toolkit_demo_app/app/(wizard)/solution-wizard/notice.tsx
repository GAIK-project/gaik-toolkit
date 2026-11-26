"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { buttonVariants } from "@/components/ui/button";
import { buildAccessRequestMailto } from "@/lib/onboarding/mailto";
import { cn } from "@/lib/utils";
import { ArrowRight, ArrowUpRight, BookOpen, Wand2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { FirstWizardTerminal } from "./first-wizard-terminal";

// Wizard V2 is the one to use: a guided chat in the browser, on a GAIK service
// of its own, where each session's agent and its PoC runs are kept apart from
// other services. It reads the demo's own accounts
// (WIZARD_SUPABASE_ACCESS=access_requests), so an approved demo account signs in
// there with the same e-mail and password. The first wizard still works: a Claude
// Code skill on anyone's own computer, and in this demo (/solution-wizard/first)
// for users an admin has granted it (`wizard_access`).
const CLASSIC_WIZARD_DOCS =
  "https://gaik-project.github.io/gaik-toolkit/guidance-layer/solution-configuration-wizard/";

/** Where the visitor's demo account stands, which decides how Wizard V2 opens. */
export type WizardAccount = "signed-out" | "pending" | "approved";

const linkClassName =
  "text-primary font-medium underline-offset-4 hover:underline";

const pressable = "transition-[background-color,scale] active:scale-[0.98]";

/** One line on how this visitor gets into Wizard V2. */
function AccessLine({ account }: { account: WizardAccount }) {
  if (account === "approved")
    return (
      <>Sign in there with your demo account&apos;s e-mail and password.</>
    );
  if (account === "pending")
    return (
      <>
        It opens with your demo account once the GAIK team has approved it, with
        the same e-mail and password.
      </>
    );
  return (
    <>
      It opens with an approved demo account, with the same e-mail and password.{" "}
      <Link href="/sign-up" className={linkClassName}>
        Create an account
      </Link>
    </>
  );
}

export function SolutionWizardNotice({
  wizardUrl,
  account,
  canRunFirstWizard,
}: {
  wizardUrl: string | null;
  account: WizardAccount;
  /** The signed-in user holds the first wizard's grant. */
  canRunFirstWizard: boolean;
}) {
  return (
    <div className="mx-auto max-w-5xl space-y-10 sm:p-6">
      <DemoPageHeader
        icon={Wand2}
        iconClassName="h-8 w-8 text-primary"
        title="Solution Configuration Wizard"
        description="Describe a business problem and get a solution built from GAIK components: a blueprint, a runnable proof of concept and its documentation."
        className="mb-0"
      />

      <section
        aria-labelledby="wizard-v2-heading"
        className="border-primary/40 from-primary/10 via-card to-card grid gap-6 rounded-2xl border-2 bg-gradient-to-br p-5 shadow-sm sm:p-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-center"
      >
        <div className="space-y-5">
          <div className="space-y-2">
            <p className="text-primary text-sm font-medium">Recommended</p>
            <h2
              id="wizard-v2-heading"
              className="font-serif text-2xl font-semibold tracking-tight"
            >
              Wizard V2
            </h2>
            <p className="text-muted-foreground leading-7">
              A guided chat in your browser, with nothing to install. It stops
              at four gates for you to check the result: requirements, solution
              design, test run and handover.
            </p>
          </div>
          <p className="text-sm leading-6">
            <AccessLine account={account} />
          </p>
          {wizardUrl ? (
            <a
              href={wizardUrl}
              rel="noopener"
              className={buttonVariants({
                size: "lg",
                className: cn("w-fit gap-2", pressable),
              })}
            >
              Open Wizard V2
              <ArrowUpRight className="size-4" />
            </a>
          ) : null}
        </div>
        <Image
          src="/solution-wizard/wizard-v2.webp"
          alt="Wizard V2 at its test run gate: the four gates along the top, the use case's process steps and workflow diagram in the middle, and the chat on the right."
          width={1440}
          height={900}
          sizes="(min-width: 1024px) 560px, 100vw"
          priority
          className="bg-background w-full rounded-xl border shadow-sm"
        />
      </section>

      <section
        aria-labelledby="first-wizard-heading"
        className="grid gap-6 border-t pt-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]"
      >
        <div className="space-y-3">
          <h2
            id="first-wizard-heading"
            className="flex items-center gap-2.5 text-lg font-semibold"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- a 20 px brand mark */}
            <img
              src="/logos/claude-code.svg"
              alt=""
              width={20}
              height={20}
              className="size-5"
            />
            Prefer Claude Code?
          </h2>
          <p className="text-muted-foreground text-sm leading-6">
            The first wizard still works as a Claude Code skill on your own
            computer, with your own Claude account. It builds the same package
            in one conversation.
          </p>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
            {canRunFirstWizard ? (
              <Link
                href="/solution-wizard/first"
                className={buttonVariants({
                  variant: "outline",
                  size: "sm",
                  className: cn("gap-2", pressable),
                })}
              >
                Start it in the browser
                <ArrowRight className="size-4" />
              </Link>
            ) : null}
            <a
              href={CLASSIC_WIZARD_DOCS}
              rel="noopener"
              className={cn(
                linkClassName,
                "inline-flex items-center gap-1.5 text-sm",
              )}
            >
              <BookOpen className="size-4" />
              How to run it
            </a>
          </div>
          {canRunFirstWizard ? (
            <p className="text-muted-foreground text-xs leading-5">
              In the browser, keep the tab open: the session and its files end
              when you leave the page.
            </p>
          ) : (
            <p className="text-muted-foreground text-sm leading-6">
              It also runs in this browser for accounts the GAIK team has opened
              it for.{" "}
              <a
                href={buildAccessRequestMailto("first wizard in the browser")}
                className={linkClassName}
              >
                Request access
              </a>
            </p>
          )}
        </div>
        <FirstWizardTerminal />
      </section>
    </div>
  );
}
