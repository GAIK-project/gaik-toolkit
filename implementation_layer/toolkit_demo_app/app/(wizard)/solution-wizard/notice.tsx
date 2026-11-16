"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { buttonVariants } from "@/components/ui/button";
import { buildAccessRequestMailto } from "@/lib/onboarding/mailto";
import { ArrowRight, ArrowUpRight, BookOpen, Wand2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { FirstWizardTerminal } from "./first-wizard-terminal";

// Two wizards. Wizard V2 is its own service, where each session's agent and its
// PoC runs are kept apart from other services, and it needs an account from the
// GAIK team. The first version is a Claude Code skill: it runs in this demo for
// users an admin has granted it (/solution-wizard/first), and on anyone's own
// computer in Claude Code.
const CLASSIC_WIZARD_DOCS =
  "https://gaik-project.github.io/gaik-toolkit/guidance-layer/solution-configuration-wizard/";

// Wizard V2's four gates, in its own words (its in-app help guide).
const GATES = [
  {
    title: "Requirements",
    detail: "What the solution must do, with what material and for whom.",
  },
  {
    title: "Solution design",
    detail: "The GAIK components chosen and the workflow diagram.",
  },
  {
    title: "Test run",
    detail: "The proof of concept runs, and you approve its result.",
  },
  {
    title: "Handover",
    detail: "The documentation and a deployment package to download.",
  },
];

export function SolutionWizardNotice({
  wizardUrl,
  canRunFirstWizard,
}: {
  wizardUrl: string | null;
  /** The signed-in user holds the first wizard's grant. */
  canRunFirstWizard: boolean;
}) {
  const requestAccess = (
    <a
      href={buildAccessRequestMailto()}
      className="text-primary font-medium underline-offset-4 hover:underline"
    >
      Request access
    </a>
  );

  return (
    <div className="mx-auto max-w-5xl space-y-6 sm:p-6">
      <DemoPageHeader
        icon={Wand2}
        iconClassName="h-8 w-8 text-primary"
        title="Solution Configuration Wizard"
        description="From a use case description to a blueprint, a runnable PoC and its documentation"
        className="mb-8"
      />

      <section
        aria-labelledby="wizard-v2-heading"
        className="from-primary/10 via-card to-card overflow-hidden rounded-2xl border bg-gradient-to-br shadow-sm"
      >
        <div className="grid gap-8 p-5 sm:p-6 md:p-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-10">
          <div className="space-y-5">
            <div className="space-y-2">
              <p className="text-primary text-sm font-medium">Recommended</p>
              <h2
                id="wizard-v2-heading"
                className="font-serif text-2xl font-semibold tracking-tight md:text-3xl"
              >
                Wizard V2
              </h2>
              <p className="text-muted-foreground">
                Describe your business problem in a chat. The wizard turns it
                into a solution built from GAIK components and stops at four
                gates for you to check the result.
              </p>
            </div>

            <div className="space-y-2.5">
              {wizardUrl ? (
                <a
                  href={wizardUrl}
                  rel="noopener"
                  className={buttonVariants({
                    size: "lg",
                    className:
                      "gap-2 transition-[background-color,scale] active:scale-[0.98]",
                  })}
                >
                  Open Wizard V2
                  <ArrowUpRight className="size-4" />
                </a>
              ) : null}
              <p className="text-muted-foreground text-sm">
                {wizardUrl
                  ? "Sign in with an account from the GAIK team. "
                  : "Wizard V2 needs an account from the GAIK team. "}
                No account yet? {requestAccess}
              </p>
            </div>
          </div>

          <ol aria-label="The four gates" className="space-y-3 lg:pt-1">
            {GATES.map((gate, index) => (
              <li key={gate.title} className="flex gap-3">
                <span
                  aria-hidden
                  className="border-primary/30 bg-background text-primary mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold tabular-nums"
                >
                  {index + 1}
                </span>
                <span className="text-sm leading-6">
                  <span className="font-medium">{gate.title}:</span>{" "}
                  <span className="text-muted-foreground">{gate.detail}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>

        <div className="px-4 md:px-8">
          <Image
            src="/solution-wizard/wizard-v2.webp"
            alt="Wizard V2 at its test run gate: the four gates along the top, the use case's process steps and workflow diagram in the middle, and the chat on the right."
            width={1440}
            height={900}
            loading="eager"
            fetchPriority="high"
            className="animate-in fade-in slide-in-from-bottom-3 bg-background w-full rounded-t-xl border border-b-0 shadow-[0_-12px_40px_-20px_rgb(15_23_42/0.25)] duration-700 ease-out motion-reduce:animate-none"
          />
        </div>
      </section>

      <section
        aria-labelledby="first-wizard-heading"
        className="bg-card space-y-6 rounded-2xl border p-5 sm:p-6 md:p-8"
      >
        <div className="max-w-2xl space-y-2">
          <h2
            id="first-wizard-heading"
            className="text-xl font-semibold tracking-tight"
          >
            The first wizard
          </h2>
          <p className="text-muted-foreground">
            The first version builds the whole package in one conversation: the
            blueprint, the workflow diagrams, a PoC and its documentation.
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-10">
          <div className="space-y-3">
            <h3 className="font-medium">In the browser</h3>
            {canRunFirstWizard ? (
              <>
                <p className="text-muted-foreground text-sm">
                  Nothing to install. Keep the tab open: the session and its
                  files end when you leave the page.
                </p>
                <Link
                  href="/solution-wizard/first"
                  className={buttonVariants({
                    variant: "outline",
                    className:
                      "gap-2 transition-[background-color,scale] active:scale-[0.98]",
                  })}
                >
                  Start the first wizard
                  <ArrowRight className="size-4" />
                </Link>
              </>
            ) : (
              <p className="text-muted-foreground text-sm">
                It runs here for accounts the GAIK team has opened it for.{" "}
                {requestAccess}
              </p>
            )}
          </div>

          <div className="space-y-3">
            <div className="flex items-center gap-2.5">
              {/* eslint-disable-next-line @next/next/no-img-element -- a 20 px brand mark */}
              <img
                src="/logos/claude-code.svg"
                alt=""
                width={20}
                height={20}
                className="size-5"
              />
              <h3 className="font-medium">On your own computer</h3>
            </div>
            <p className="text-muted-foreground text-sm">
              It is a Claude Code skill in the gaik-toolkit repository and runs
              with your own Claude account, no GAIK account needed.
            </p>
            <FirstWizardTerminal />
            <a
              href={CLASSIC_WIZARD_DOCS}
              rel="noopener"
              className="text-primary inline-flex items-center gap-1.5 text-sm font-medium underline-offset-4 hover:underline"
            >
              <BookOpen className="size-4" />
              How to run it
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
