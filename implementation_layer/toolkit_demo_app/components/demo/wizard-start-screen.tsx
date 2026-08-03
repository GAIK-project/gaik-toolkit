"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import {
  FileAudio,
  FileText,
  Loader2,
  MessagesSquare,
  RotateCcw,
  Table2,
  Wand2,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

/**
 * Starting points offered on the empty screen. Clicking one sends it as the
 * first message, so the wording is what a user would actually type, not a
 * marketing headline.
 */
const EXAMPLES = [
  {
    icon: FileAudio,
    title: "Voice to tickets",
    prompt:
      "We receive voice recordings from field technicians and want to turn them into structured maintenance tickets.",
  },
  {
    icon: FileText,
    title: "Invoice fields",
    prompt: "We need to extract the key fields from incoming supplier PDF invoices.",
  },
  {
    icon: MessagesSquare,
    title: "Policy Q&A",
    prompt: "We want a question-answering assistant over our internal policy documents.",
  },
  {
    icon: Table2,
    title: "Multi-source report",
    prompt:
      "We need to generate a multi-section analysis report from uploaded documents, transcripts and data files.",
  },
] as const;

/**
 * The screen shown before the first user message.
 *
 * This exists because the welcome used to be injected as a fake assistant
 * message inside the chat log, so users could not tell whether they were
 * reading the wizard talking or a static intro. Here it is unmistakably a
 * start screen: it lives outside the conversation, and it disappears the
 * moment a real conversation begins.
 */
export function WizardStartScreen({
  connecting,
  disabled,
  error,
  onRetry,
  onPickExample,
  composer,
}: {
  connecting: boolean;
  disabled: boolean;
  error: string | null;
  onRetry: () => void;
  onPickExample: (prompt: string) => void;
  composer: ReactNode;
}) {
  const reduce = useReducedMotion();

  // Staggered entry: the eye lands on the mark, then the question, then the
  // starting points, then the input it should type into. One pass, no loop.
  const rise = (delay: number) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 8 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.4, delay, ease: [0.16, 1, 0.3, 1] as const },
        };

  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-8">
      <div className="w-full max-w-2xl">
        <motion.div {...rise(0)} className="flex flex-col items-center text-center">
          <span className="bg-primary/10 text-primary flex h-11 w-11 items-center justify-center rounded-2xl">
            <Wand2 className="h-5 w-5" />
          </span>
          <h2 className="mt-4 text-xl font-semibold tracking-tight">
            What should your GenAI solution do?
          </h2>
          <p className="text-muted-foreground mt-2 max-w-md text-sm">
            Describe the task in plain language. The wizard asks follow-up questions, then
            builds the blueprint, diagrams, docs and a runnable proof of concept.
          </p>
        </motion.div>

        <motion.div {...rise(0.08)} className="mt-6">
          {error ? (
            <Alert variant="destructive" role="alert">
              <AlertTitle>The wizard could not be started</AlertTitle>
              <AlertDescription>
                <span className="block">{error}</span>
                <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
                  <RotateCcw className="mr-1 h-4 w-4" />
                  Try again
                </Button>
              </AlertDescription>
            </Alert>
          ) : connecting ? (
            // Deliberately no composer and no example buttons here. Showing a
            // typable-looking input that silently rejects input is the most
            // confusing state this screen can be in, so while the session is
            // coming up there is exactly one thing on screen: the wait.
            <div
              aria-live="polite"
              className="text-muted-foreground flex items-center justify-center gap-2 py-10 text-sm"
            >
              <Loader2 className="text-primary h-4 w-4 animate-spin" />
              <span>Preparing your workspace…</span>
            </div>
          ) : (
            <>
              <p className="text-muted-foreground mb-3 text-center text-xs">
                Or start from an example
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {EXAMPLES.map((e) => (
                  <button
                    key={e.title}
                    type="button"
                    disabled={disabled}
                    onClick={() => onPickExample(e.prompt)}
                    className="group hover:border-primary/40 hover:bg-accent/40 focus-visible:ring-ring flex items-start gap-3 rounded-xl border p-3 text-left transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
                  >
                    <e.icon className="text-muted-foreground group-hover:text-primary mt-0.5 h-4 w-4 shrink-0 transition-colors" />
                    <span className="min-w-0">
                      <span className="block text-sm font-medium">{e.title}</span>
                      <span className="text-muted-foreground line-clamp-2 block text-xs">
                        {e.prompt}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </motion.div>

        {!connecting && !error && (
          <motion.div {...rise(0.16)} className="mt-6">
            {composer}
          </motion.div>
        )}
      </div>
    </div>
  );
}
