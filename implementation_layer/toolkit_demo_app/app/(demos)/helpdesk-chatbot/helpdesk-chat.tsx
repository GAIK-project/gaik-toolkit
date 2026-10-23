"use client";

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { Message, MessageContent } from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
} from "@/components/ai-elements/prompt-input";
import { Button } from "@/components/ui/button";
import type { HelpdeskUIMessage } from "@/lib/helpdesk-chatbot/agent";
import { cn } from "@/lib/utils";
import { useChat } from "@ai-sdk/react";
import {
  DefaultChatTransport,
  lastAssistantMessageIsCompleteWithApprovalResponses,
} from "ai";
import { Headset, Loader2, Play, RotateCcw, Square } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { AssistantMessage } from "./assistant-message";
import { DEMO_STEPS, playDemo } from "./demo-playback";
import type { DemoFill } from "./tool-cards";

const STARTERS = [
  "We are a 12-person machine shop. Where should we start with AI?",
  "Do you have training for our staff?",
  "Mitä tapahtuu yrityksemme datalle pilotissa?",
  "I'd like to talk to someone about funding.",
];

// Route errors are fixed sentences written in route.ts; anything else (a proxy
// page, a stack trace) is replaced, never shown.
const KNOWN_ERRORS = new Set([
  "Sign in to use this feature.",
  "Your access is pending approval.",
  "The chatbot is not configured.",
  "Too many requests. Try again in a minute.",
  "The conversation is too long. Start a new one.",
]);

function errorText(error: Error): string {
  try {
    const { error: message } = JSON.parse(error.message);
    if (KNOWN_ERRORS.has(message)) return message;
  } catch {
    // not JSON: fall through
  }
  return "The assistant could not answer. Please try again.";
}

interface DemoState {
  messages: HelpdeskUIMessage[];
  streamingId: string | null;
  caption: { step: number; text: string } | null;
  fill: DemoFill | null;
  playing: boolean;
}

const EMPTY_DEMO: DemoState = {
  messages: [],
  streamingId: null,
  caption: null,
  fill: null,
  playing: true,
};

function Welcome({
  onPick,
  onDemo,
}: {
  onPick: (text: string) => void;
  onDemo: () => void;
}) {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-5 py-8 text-center">
      <motion.div
        initial={{ scale: 0.6, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 22 }}
        className="bg-primary/10 text-primary ring-primary/15 grid size-14 place-items-center rounded-2xl ring-1 ring-inset"
      >
        <Headset className="size-7" />
      </motion.div>
      <div className="space-y-1.5">
        <h2 className="font-serif text-xl font-semibold">How can we help?</h2>
        <p className="text-muted-foreground text-sm text-balance">
          Ask about services, prices or how to get started, in English or
          Finnish. Answers come from the hub&apos;s own catalogue, and a person
          can take over when needed.
        </p>
      </div>
      <Button onClick={onDemo} className="gap-2 rounded-full">
        <Play className="size-4" />
        Watch a demo conversation
      </Button>
      <div className="flex w-full flex-col gap-2">
        <p className="text-muted-foreground text-xs">or ask one of these</p>
        {STARTERS.map((s, i) => (
          <motion.button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 * i + 0.1 }}
            className="border-border/60 bg-card hover:border-primary/40 hover:bg-primary/5 rounded-xl border px-4 py-2.5 text-left text-sm transition-colors"
          >
            {s}
          </motion.button>
        ))}
      </div>
    </div>
  );
}

/** The narration above the chat while the demo plays, with step progress. */
function DemoCaption({
  caption,
  playing,
}: {
  caption: { step: number; text: string };
  playing: boolean;
}) {
  return (
    <div className="bg-primary/5 flex items-center gap-3 border-b px-4 py-2.5">
      <span className="bg-primary text-primary-foreground grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold">
        {caption.step}
      </span>
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.p
          key={caption.text}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.25 }}
          className="min-w-0 flex-1 text-sm font-medium"
          aria-live="polite"
        >
          {caption.text}
        </motion.p>
      </AnimatePresence>
      <div className="hidden shrink-0 gap-1 sm:flex" aria-hidden>
        {Array.from({ length: DEMO_STEPS }, (_, i) => (
          <span
            key={i}
            className={cn(
              "h-1.5 w-4 rounded-full transition-colors",
              i < caption.step ? "bg-primary" : "bg-primary/20",
              playing && i === caption.step - 1 && "animate-pulse",
            )}
          />
        ))}
      </div>
    </div>
  );
}

export function HelpdeskChat() {
  const [input, setInput] = useState("");
  const [demo, setDemo] = useState<DemoState | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const {
    messages,
    sendMessage,
    regenerate,
    status,
    stop,
    error,
    setMessages,
    clearError,
    addToolApprovalResponse,
  } = useChat<HelpdeskUIMessage>({
    transport: new DefaultChatTransport({ api: "/api/helpdesk-chat" }),
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithApprovalResponses,
    experimental_throttle: 50,
  });

  useEffect(() => () => abortRef.current?.abort(), []);

  const busy = status === "submitted" || status === "streaming";
  const playing = demo?.playing ?? false;
  const shown = demo ? demo.messages : messages;

  function stopDemo() {
    abortRef.current?.abort();
    abortRef.current = null;
    setDemo(null);
    setInput("");
  }

  function startDemo() {
    stopDemo();
    stop();
    clearError();
    setMessages([]);
    const controller = new AbortController();
    abortRef.current = controller;
    setDemo(EMPTY_DEMO);
    const update = (patch: Partial<DemoState>) =>
      setDemo((d) => (d ? { ...d, ...patch } : d));
    playDemo({
      signal: controller.signal,
      setMessages: (m) => update({ messages: m }),
      setInput,
      setCaption: (caption) => update({ caption }),
      setStreamingId: (streamingId) => update({ streamingId }),
      setDemoFill: (fill) => update({ fill }),
    })
      .then(() => update({ playing: false }))
      .catch(() => {
        // stopped
      });
  }

  function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy || playing) return;
    if (demo) stopDemo();
    clearError();
    void sendMessage({ text: trimmed });
    setInput("");
  }

  function reset() {
    stopDemo();
    stop();
    clearError();
    setMessages([]);
  }

  return (
    <div className="bg-card flex h-[min(76vh,800px)] min-h-[520px] flex-col overflow-hidden rounded-2xl border shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="bg-primary text-primary-foreground grid size-9 place-items-center rounded-full">
            <Headset className="size-[18px]" />
          </div>
          <div className="leading-tight">
            <p className="text-sm font-semibold">Lakeside AI Hub Helpdesk</p>
            <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              AI assistant · a person can take over
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {playing ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={stopDemo}
              className="text-muted-foreground gap-1.5"
            >
              <Square className="size-3.5" />
              Stop demo
            </Button>
          ) : (
            shown.length > 0 && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={startDemo}
                  className="text-muted-foreground gap-1.5"
                >
                  <Play className="size-3.5" />
                  {demo ? "Replay demo" : "Watch demo"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={reset}
                  className="text-muted-foreground gap-1.5"
                >
                  <RotateCcw className="size-3.5" />
                  New conversation
                </Button>
              </>
            )
          )}
        </div>
      </div>

      {demo?.caption && (
        <DemoCaption caption={demo.caption} playing={playing} />
      )}

      <Conversation>
        <ConversationContent className="gap-6 px-4 py-5 sm:px-6">
          {shown.length === 0 && !demo ? (
            <Welcome onPick={send} onDemo={startDemo} />
          ) : (
            shown.map((message, index) => {
              const isLast = index === shown.length - 1;
              return message.role === "user" ? (
                <motion.div
                  key={message.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <Message from="user">
                    <MessageContent className="bg-primary! text-primary-foreground! rounded-2xl! rounded-br-md!">
                      <span className="whitespace-pre-wrap">
                        {message.parts
                          .map((p) => (p.type === "text" ? p.text : ""))
                          .join("")}
                      </span>
                    </MessageContent>
                  </Message>
                </motion.div>
              ) : (
                <AssistantMessage
                  key={message.id}
                  message={message}
                  streaming={
                    demo ? demo.streamingId === message.id : isLast && busy
                  }
                  onApproval={demo ? () => {} : addToolApprovalResponse}
                  onRegenerate={
                    !demo && isLast && !busy
                      ? () => void regenerate()
                      : undefined
                  }
                  demoFill={demo?.fill}
                  demo={Boolean(demo)}
                />
              );
            })
          )}
          {!demo &&
            status === "submitted" &&
            messages.at(-1)?.role === "user" && (
              <div className="text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
              </div>
            )}
          {!demo && error && (
            <p className="text-destructive text-sm" role="alert">
              {errorText(error)}
            </p>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <div className="p-3 pt-0">
        <PromptInput onSubmit={({ text }) => send(text)}>
          <PromptInputBody>
            <PromptInputTextarea
              value={input}
              onChange={(e) => setInput(e.currentTarget.value)}
              placeholder="Ask the helpdesk…"
              maxLength={2000}
              readOnly={playing}
            />
          </PromptInputBody>
          <PromptInputFooter className="justify-between">
            <span className="text-muted-foreground px-2 text-xs">
              {playing
                ? "Demo playback · no AI calls are made"
                : "AI can make mistakes. Check important details with the team."}
            </span>
            <PromptInputSubmit
              status={status}
              onStop={stop}
              disabled={playing || (!busy && !input.trim())}
            />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}
