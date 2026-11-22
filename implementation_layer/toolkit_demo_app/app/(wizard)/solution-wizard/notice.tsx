"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { buttonVariants } from "@/components/ui/button";
import {
  buildAccessRequestMailto,
  GAIK_CONTACT_EMAIL,
  GAIK_CONTACT_URL,
} from "@/lib/onboarding/mailto";
import { cn } from "@/lib/utils";
import { ArrowRight, ArrowUpRight, BookOpen, Wand2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { FirstWizardTerminal } from "./first-wizard-terminal";

// Two wizards, side by side with the same three facts, so a visitor sees at once
// which one fits and how to get in. Wizard V2 is its own service, where each
// session's agent and its PoC runs are kept apart from other services, and it
// needs an account from the GAIK team; the demo's sign-in does not open it. The
// first version is a Claude Code skill: it runs on anyone's own computer in Claude
// Code, and in this demo (/solution-wizard/first) for users an admin has granted
// it (`wizard_access`).
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

const cardClassName =
  "flex flex-col gap-5 rounded-2xl border p-5 shadow-sm sm:p-6";

const linkClassName =
  "text-primary font-medium underline-offset-4 hover:underline";

/** The same three facts for each wizard, as label and value rows. */
function Facts({ rows }: { rows: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="divide-y border-y text-sm">
      {rows.map(({ label, value }) => (
        <div
          key={label}
          className="grid gap-1 py-3 sm:grid-cols-[8rem_minmax(0,1fr)] sm:gap-4"
        >
          <dt className="text-muted-foreground font-medium">{label}</dt>
          <dd className="space-y-1.5 leading-6">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SolutionWizardNotice({
  wizardUrl,
  canRunFirstWizard,
}: {
  wizardUrl: string | null;
  /** The signed-in user holds the first wizard's grant. */
  canRunFirstWizard: boolean;
}) {
  return (
    <div className="mx-auto max-w-5xl space-y-6 sm:p-6">
      <DemoPageHeader
        icon={Wand2}
        iconClassName="h-8 w-8 text-primary"
        title="Solution Configuration Wizard"
        description="Two versions turn a use case description into a blueprint, a runnable PoC and its documentation."
        className="mb-8"
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <section
          aria-labelledby="wizard-v2-heading"
          className={cn(
            cardClassName,
            "border-primary/40 from-primary/10 via-card to-card border-2 bg-gradient-to-br",
          )}
        >
          <div className="space-y-2">
            <h2
              id="wizard-v2-heading"
              className="flex items-center gap-3 font-serif text-2xl font-semibold tracking-tight"
            >
              <span className="bg-primary text-primary-foreground flex size-9 shrink-0 items-center justify-center rounded-lg shadow-sm">
                <Wand2 className="size-5" />
              </span>
              Wizard V2
            </h2>
            <p className="text-muted-foreground">
              A guided chat that turns your business problem into a solution
              built from GAIK components. It stops at four gates for you to
              check the result.
            </p>
          </div>

          <Facts
            rows={[
              {
                label: "Who it is for",
                value:
                  "Anyone with a use case in mind. No coding and nothing to install.",
              },
              {
                label: "Where it runs",
                value: "In your browser, on a GAIK service of its own.",
              },
              {
                label: "Access",
                value: (
                  <p>
                    An account from the GAIK team. Your sign-in to this demo
                    does not open it.{" "}
                    <a
                      href={buildAccessRequestMailto("Wizard V2")}
                      className={linkClassName}
                    >
                      Request an account
                    </a>
                  </p>
                ),
              },
            ]}
          />

          {wizardUrl ? (
            <a
              href={wizardUrl}
              rel="noopener"
              className={buttonVariants({
                size: "lg",
                className:
                  "w-fit gap-2 transition-[background-color,scale] active:scale-[0.98]",
              })}
            >
              Open Wizard V2
              <ArrowUpRight className="size-4" />
            </a>
          ) : null}

          <ol aria-label="The four gates" className="space-y-3 border-t pt-5">
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
        </section>

        <section
          aria-labelledby="first-wizard-heading"
          className={cn(cardClassName, "bg-card")}
        >
          <div className="space-y-2">
            <h2
              id="first-wizard-heading"
              className="flex items-center gap-3 font-serif text-2xl font-semibold tracking-tight"
            >
              <span className="bg-muted flex size-9 shrink-0 items-center justify-center rounded-lg">
                {/* eslint-disable-next-line @next/next/no-img-element -- a 20 px brand mark */}
                <img
                  src="/logos/claude-code.svg"
                  alt=""
                  width={20}
                  height={20}
                  className="size-5"
                />
              </span>
              First wizard
            </h2>
            <p className="text-muted-foreground">
              The first version, a Claude Code skill. It builds the whole
              package in one conversation: the blueprint, the workflow diagrams,
              a PoC and its documentation.
            </p>
          </div>

          <Facts
            rows={[
              {
                label: "Who it is for",
                value: "Developers who use Claude Code.",
              },
              {
                label: "Where it runs",
                value:
                  "In Claude Code on your own computer, or in this demo's browser.",
              },
              {
                label: "Access",
                value: (
                  <>
                    <p>
                      In Claude Code: your own Claude account, no GAIK account
                      needed.
                    </p>
                    <p>
                      In the browser:{" "}
                      {canRunFirstWizard ? (
                        "your account has access."
                      ) : (
                        <>
                          a demo account the GAIK team has opened it for.{" "}
                          <a
                            href={buildAccessRequestMailto(
                              "first wizard in the browser",
                            )}
                            className={linkClassName}
                          >
                            Request access
                          </a>
                        </>
                      )}
                    </p>
                  </>
                ),
              },
            ]}
          />

          <div className="mt-auto space-y-3">
            <FirstWizardTerminal />
            <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
              {canRunFirstWizard ? (
                <Link
                  href="/solution-wizard/first"
                  className={buttonVariants({
                    variant: "outline",
                    className:
                      "gap-2 transition-[background-color,scale] active:scale-[0.98]",
                  })}
                >
                  Start in the browser
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
              <p className="text-muted-foreground text-sm">
                In the browser, keep the tab open: the session and its files end
                when you leave the page.
              </p>
            ) : null}
          </div>
        </section>
      </div>

      {/* The request links above open a mail app; this works without one. */}
      <p className="text-muted-foreground text-sm">
        Requests go to{" "}
        <a href={`mailto:${GAIK_CONTACT_EMAIL}`} className={linkClassName}>
          {GAIK_CONTACT_EMAIL}
        </a>
        , or write through the{" "}
        <a
          href={GAIK_CONTACT_URL}
          target="_blank"
          rel="noopener noreferrer"
          className={linkClassName}
        >
          GAIK contact page
        </a>
        .
      </p>

      <figure className="space-y-2">
        <Image
          src="/solution-wizard/wizard-v2.webp"
          alt="Wizard V2 at its test run gate: the four gates along the top, the use case's process steps and workflow diagram in the middle, and the chat on the right."
          width={1440}
          height={900}
          sizes="(min-width: 1024px) 976px, 100vw"
          className="bg-background w-full rounded-xl border shadow-sm"
        />
        <figcaption className="text-muted-foreground text-sm">
          Wizard V2 at its test run gate.
        </figcaption>
      </figure>
    </div>
  );
}
