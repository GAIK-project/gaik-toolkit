"use client";

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
} from "@/components/ai-elements/prompt-input";
import { BlurFade } from "@/components/ui/blur-fade";
import { BorderBeam } from "@/components/ui/border-beam";
import { Button } from "@/components/ui/button";
import { DotPattern } from "@/components/ui/dot-pattern";
import { ShimmerButton } from "@/components/ui/shimmer-button";
import { Textarea } from "@/components/ui/textarea";
import type { ScreeningUIMessage } from "@/lib/ai-act-screening/agent";
import type { Screening } from "@/lib/ai-act-screening/types";
import { cn } from "@/lib/utils";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import {
  ArrowRight,
  Download,
  FlaskConical,
  Hammer,
  Lightbulb,
  Loader2,
  MessagesSquare,
  RotateCcw,
  Rocket,
  ReceiptText,
  ScanSearch,
  ShieldCheck,
  Users,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import { ScreeningResults } from "./results";

const KNOWN_ERRORS = new Set([
  "Sign in to use this feature.",
  "Your access is pending approval.",
  "The screening is not configured.",
  "Too many requests. Try again in a minute.",
  "The conversation is too long. Start a new one.",
  "A message is too long. Shorten it and try again.",
]);

function errorText(error: Error): string {
  try {
    const { error: message } = JSON.parse(error.message);
    if (KNOWN_ERRORS.has(message)) return message;
    if (
      typeof message === "string" &&
      message.endsWith("Full access opens when your account is approved.")
    )
      return message;
  } catch {
    // not JSON: fall through
  }
  return "The screening could not continue. Please try again.";
}

const STAGES = [
  { id: "idea", label: "An idea", icon: Lightbulb },
  { id: "development", label: "Being built", icon: Hammer },
  { id: "pilot", label: "A pilot with real users", icon: FlaskConical },
  { id: "production", label: "In regular use", icon: Rocket },
] as const;

const EXAMPLES = [
  {
    title: "CV screening tool",
    stage: "production",
    icon: Users,
    text: "We use an AI tool to read CVs for our open positions. It gives each applicant a match score and a short summary, and the recruiter looks at the top ten.",
  },
  {
    title: "Customer support chatbot",
    stage: "development",
    icon: MessagesSquare,
    text: "We are building a chatbot for our webshop that answers customers' questions about orders and returns using our FAQ, and hands over to a person when it cannot help.",
  },
  {
    title: "Invoice data extraction",
    stage: "pilot",
    icon: ReceiptText,
    text: "We are piloting an AI tool that reads supplier invoices and extracts the supplier, dates, line items and totals into our accounting system. Our accounting staff check the extracted values before they are posted.",
  },
];

interface Result {
  key: string;
  name: string;
  screening: Screening;
}

/** The latest screening that passed the checker, read from the tool results. */
function latestResult(messages: ScreeningUIMessage[]): Result | null {
  let found: Result | null = null;
  for (const message of messages) {
    for (const part of message.parts) {
      if (
        part.type === "tool-submitScreening" &&
        part.state === "output-available" &&
        part.output.ok &&
        part.output.screening
      ) {
        found = {
          key: part.toolCallId,
          name: part.input.intake.use_case_name,
          screening: part.output.screening as unknown as Screening,
        };
      }
    }
  }
  return found;
}

function Start({ onStart }: { onStart: (text: string) => void }) {
  const [text, setText] = useState("");
  const [stage, setStage] = useState<string>("");
  const ready = text.trim().length >= 20 && stage !== "";
  return (
    <div className="relative">
      <DotPattern
        aria-hidden
        className="text-primary/20 -z-10 [mask-image:radial-gradient(520px_circle_at_center,white,transparent)]"
      />

      <div className="bg-card relative overflow-hidden rounded-3xl border shadow-lg">
        <BorderBeam
          size={220}
          duration={9}
          colorFrom="var(--color-primary)"
          colorTo="#38bdf8"
        />
        <div className="space-y-7 p-6 sm:p-9">
          <BlurFade delay={0.1}>
            <div className="flex flex-wrap items-start justify-between gap-3 sm:flex-nowrap">
              <div className="max-w-2xl">
                <h2 className="font-serif text-2xl font-semibold">
                  Describe the AI use case
                </h2>
                <p className="text-muted-foreground mt-1.5 text-sm">
                  What it does or will do, who uses it, what information it
                  works on and what happens with its output. The agent then asks
                  a few short follow-up questions.
                </p>
              </div>
              <Button asChild variant="ghost" size="sm" className="gap-1.5">
                <a
                  href="/downloads/skills/ai-act-use-case-screening.zip"
                  download
                >
                  <Download className="size-3.5" />
                  Download the skill
                </a>
              </Button>
            </div>
          </BlurFade>

          <BlurFade delay={0.15}>
            <p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
              Start from an example
            </p>
            <div className="grid gap-3 sm:grid-cols-3">
              {EXAMPLES.map((e) => {
                const Icon = e.icon;
                const active = text === e.text;
                return (
                  <motion.button
                    key={e.title}
                    type="button"
                    whileHover={{ y: -3 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => {
                      setText(e.text);
                      setStage(e.stage);
                    }}
                    className={cn(
                      "group flex items-start gap-3 rounded-2xl border p-3.5 text-left transition-colors",
                      active
                        ? "border-primary bg-primary/10"
                        : "hover:border-primary/50 hover:bg-primary/5",
                    )}
                  >
                    <span className="bg-primary/10 text-primary grid size-9 shrink-0 place-items-center rounded-xl">
                      <Icon className="size-4" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold">
                        {e.title}
                      </span>
                      <span className="text-muted-foreground line-clamp-2 text-xs">
                        {e.text}
                      </span>
                    </span>
                  </motion.button>
                );
              })}
            </div>
          </BlurFade>

          <BlurFade delay={0.2}>
            <div className="relative">
              <Textarea
                value={text}
                onChange={(e) => setText(e.currentTarget.value)}
                rows={6}
                maxLength={4000}
                placeholder="Or write your own: We use an AI tool to …"
                aria-label="Description of the AI use case"
                className="border-border bg-background focus-visible:border-primary resize-none rounded-2xl border-2 p-4 pb-8 text-base shadow-sm"
              />
              <span className="text-muted-foreground absolute right-3 bottom-2 text-xs tabular-nums">
                {text.length}/4000
              </span>
            </div>
          </BlurFade>

          <BlurFade delay={0.25}>
            <fieldset>
              <legend className="mb-2 text-sm font-medium">
                Where is it today?
              </legend>
              <div className="grid gap-2.5 sm:grid-cols-4">
                {STAGES.map((s) => {
                  const Icon = s.icon;
                  const selected = stage === s.id;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => setStage(s.id)}
                      className={cn(
                        "relative flex flex-col items-center gap-1.5 rounded-2xl border px-3 py-3.5 text-center text-sm font-medium transition-colors",
                        selected
                          ? "text-primary"
                          : "text-muted-foreground hover:border-primary/50 hover:text-foreground",
                      )}
                    >
                      {selected && (
                        <motion.span
                          layoutId="stage-highlight"
                          className="border-primary bg-primary/10 absolute inset-0 rounded-2xl border-2"
                          transition={{
                            type: "spring",
                            stiffness: 380,
                            damping: 30,
                          }}
                        />
                      )}
                      <Icon className="relative size-5" />
                      <span className="relative">{s.label}</span>
                    </button>
                  );
                })}
              </div>
            </fieldset>
          </BlurFade>

          <BlurFade delay={0.3}>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <p className="text-muted-foreground flex items-center gap-2 text-xs">
                <ShieldCheck className="mt-0.5 size-4 shrink-0" />
                Do not enter personal data or confidential material. This is a
                preliminary screening, not legal advice.
              </p>
              <ShimmerButton
                disabled={!ready}
                onClick={() => {
                  const label = STAGES.find((s) => s.id === stage)?.label ?? "";
                  onStart(`${text.trim()}\n\nStage: ${label}.`);
                }}
                background="var(--color-primary)"
                className="gap-2 px-7 py-3 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-40"
              >
                Start the screening
                <ArrowRight className="size-4" />
              </ShimmerButton>
            </div>
          </BlurFade>
        </div>
      </div>
    </div>
  );
}

function Chat({
  messages,
  status,
  error,
  onSend,
  onStop,
  result,
  onShowResults,
}: {
  messages: ScreeningUIMessage[];
  status: ReturnType<typeof useChat<ScreeningUIMessage>>["status"];
  error: Error | undefined;
  onSend: (text: string) => void;
  onStop: () => void;
  result: Result | null;
  onShowResults: () => void;
}) {
  const [input, setInput] = useState("");
  const busy = status === "submitted" || status === "streaming";
  const checking = messages
    .at(-1)
    ?.parts.some(
      (p) =>
        p.type === "tool-submitScreening" &&
        (p.state === "input-streaming" || p.state === "input-available"),
    );
  return (
    <div className="bg-card flex h-[min(74vh,760px)] min-h-[480px] flex-col overflow-hidden rounded-2xl border shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <ScanSearch className="text-primary size-4" />
          AI Act screening
          <span className="text-muted-foreground font-normal">
            · answer briefly, skip, or say “don’t know”
          </span>
        </p>
        {result && (
          <Button size="sm" onClick={onShowResults}>
            Show the results
          </Button>
        )}
      </div>
      <Conversation>
        <ConversationContent className="gap-5 px-4 py-5 sm:px-6">
          {messages.map((message) => {
            const text = message.parts
              .map((p) => (p.type === "text" ? p.text : ""))
              .join("");
            if (message.role === "user")
              return (
                <Message key={message.id} from="user">
                  <MessageContent className="bg-primary! text-primary-foreground! rounded-2xl! rounded-br-md!">
                    <span className="whitespace-pre-wrap">{text}</span>
                  </MessageContent>
                </Message>
              );
            return (
              <div key={message.id} className="space-y-2">
                {text.trim() && <MessageResponse>{text}</MessageResponse>}
              </div>
            );
          })}
          {busy && (
            <div
              className="text-muted-foreground flex items-center gap-2 text-sm"
              aria-live="polite"
            >
              <Loader2 className="size-3.5 animate-spin" />
              {checking
                ? "Checking the screening against the skill’s rules…"
                : "Thinking…"}
            </div>
          )}
          {error && (
            <p className="text-destructive text-sm" role="alert">
              {errorText(error)}
            </p>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>
      <div className="p-3 pt-0">
        <PromptInput
          onSubmit={({ text }) => {
            const t = text.trim();
            if (!t || busy) return;
            onSend(t);
            setInput("");
          }}
        >
          <PromptInputBody>
            <PromptInputTextarea
              value={input}
              onChange={(e) => setInput(e.currentTarget.value)}
              placeholder="Your answer…"
              maxLength={4000}
            />
          </PromptInputBody>
          <PromptInputFooter className="justify-between">
            <span className="text-muted-foreground px-2 text-xs">
              Results are generated by AI and can be wrong. Check them before
              you use them.
            </span>
            <PromptInputSubmit
              status={status}
              onStop={onStop}
              disabled={!busy && !input.trim()}
            />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}

export function ScreeningDemo() {
  const {
    messages,
    sendMessage,
    status,
    stop,
    error,
    setMessages,
    clearError,
  } = useChat<ScreeningUIMessage>({
    transport: new DefaultChatTransport({ api: "/api/ai-act-screening" }),
    experimental_throttle: 50,
  });
  const result = useMemo(() => latestResult(messages), [messages]);
  // The user can step back from a result to the conversation; a new passed
  // screening (a new key) opens the results again.
  const [chatKey, setChatKey] = useState<string | null>(null);
  const showResults = result !== null && chatKey !== result.key;

  function restart() {
    stop();
    clearError();
    setMessages([]);
    setChatKey(null);
  }

  function send(text: string) {
    clearError();
    void sendMessage({ text });
  }

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={messages.length === 0 ? "start" : showResults ? "results" : "chat"}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
      >
        {messages.length === 0 ? (
          <>
            <Start onStart={send} />
            {error && (
              <p className="text-destructive mt-3 text-sm" role="alert">
                {errorText(error)}
              </p>
            )}
          </>
        ) : showResults && result ? (
          <ScreeningResults
            screening={result.screening}
            name={result.name}
            onBackToChat={() => setChatKey(result.key)}
            onRestart={restart}
          />
        ) : (
          <div className="space-y-3">
            <Chat
              messages={messages}
              status={status}
              error={error}
              onSend={send}
              onStop={stop}
              result={result}
              onShowResults={() => setChatKey(null)}
            />
            <div className="flex justify-end">
              <Button
                variant="ghost"
                size="sm"
                onClick={restart}
                className="text-muted-foreground gap-1.5"
              >
                <RotateCcw className="size-3.5" />
                Start over
              </Button>
            </div>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
