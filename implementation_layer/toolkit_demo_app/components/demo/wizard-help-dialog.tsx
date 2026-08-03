"use client";

import { HelpCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

/**
 * The wizard is a long, unfamiliar process, and the start screen deliberately
 * says very little. This is where the rest of the explanation lives: available
 * on demand, out of the way until asked for.
 */
export function WizardHelpDialog() {
  return (
    <Dialog>
      {/* No tooltip wrapper: nesting two `asChild` triggers swallows the click,
          and a tooltip that repeats the aria-label on a button whose whole job
          is to explain itself adds nothing. */}
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="text-muted-foreground hover:text-foreground h-7 w-7"
          aria-label="What is this wizard?"
          title="What is this wizard?"
        >
          <HelpCircle className="h-4 w-4" />
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>How the Solution Configuration Wizard works</DialogTitle>
          <DialogDescription>
            It turns a plain-language use case into a proof of concept you can run.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 text-sm">
          <section>
            <h3 className="font-medium">What you do</h3>
            <p className="text-muted-foreground mt-1">
              Describe the task in your own words, then answer the follow-up questions.
              You can attach documents, audio or spreadsheets if they help explain the
              input. There is no form to fill in.
            </p>
          </section>

          <section>
            <h3 className="font-medium">What it does</h3>
            <p className="text-muted-foreground mt-1">
              It collects the requirements, picks the GAIK components that fit, assembles
              a validated blueprint, and scaffolds a proof of concept. The progress bar
              above the conversation tracks which stage the run has reached.
            </p>
          </section>

          <section>
            <h3 className="font-medium">What you get</h3>
            <p className="text-muted-foreground mt-1">
              A blueprint, workflow diagrams, an extraction schema where one is needed,
              runnable Python, and documentation. Files appear in the panel on the right
              as they are written; each one is downloadable, or take the whole set as a
              zip.
            </p>
          </section>

          <section>
            <h3 className="font-medium">How long it takes</h3>
            <p className="text-muted-foreground mt-1">
              The questions take a few minutes. Building the proof of concept runs for
              several minutes more, with long quiet stretches while the wizard writes and
              checks files. That is expected. Keep the tab open: the session is lost on
              reload.
            </p>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
