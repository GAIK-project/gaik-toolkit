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
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Button } from "@/components/ui/button";
import type { HelpdeskUIMessage } from "@/lib/helpdesk-chatbot/agent";
import { useChat } from "@ai-sdk/react";
import {
  DefaultChatTransport,
  lastAssistantMessageIsCompleteWithApprovalResponses,
} from "ai";
import { Headset, RotateCcw } from "lucide-react";
import { useState } from "react";
import { HandoffCard, ServiceList, SourceList } from "./tool-cards";

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

function AssistantMessage({
  message,
  onApproval,
}: {
  message: HelpdeskUIMessage;
  onApproval: (response: {
    id: string;
    approved: boolean;
    reason?: string;
  }) => void;
}) {
  return (
    <>
      {message.parts.map((part, i) => {
        const key = `${message.id}-${i}`;
        switch (part.type) {
          case "text":
            return part.text ? (
              <MessageResponse key={key}>{part.text}</MessageResponse>
            ) : null;
          case "tool-searchServices":
            return <ServiceList key={key} part={part} />;
          case "tool-searchKnowledge":
            return <SourceList key={key} part={part} />;
          case "tool-requestHumanHandoff":
            return (
              <HandoffCard key={key} part={part} onApproval={onApproval} />
            );
          default:
            return null;
        }
      })}
    </>
  );
}

export function HelpdeskChat() {
  const [input, setInput] = useState("");
  const {
    messages,
    sendMessage,
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

  const busy = status === "submitted" || status === "streaming";
  const last = messages.at(-1);
  // "Thinking" until the assistant has put something on screen.
  const waiting =
    status === "submitted" ||
    (status === "streaming" &&
      last?.role === "assistant" &&
      !last.parts.some((p) => p.type === "text" && p.text));

  function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    clearError();
    void sendMessage({ text: trimmed });
    setInput("");
  }

  function reset() {
    stop();
    clearError();
    setMessages([]);
  }

  return (
    <div className="bg-card flex h-[min(72vh,760px)] min-h-[480px] flex-col overflow-hidden rounded-xl border">
      <div className="flex items-center justify-between border-b px-4 py-2.5">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Headset className="text-primary size-4" />
          Lakeside AI Hub · Helpdesk
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={reset}
          disabled={messages.length === 0}
          className="text-muted-foreground gap-1.5"
        >
          <RotateCcw className="size-3.5" />
          New conversation
        </Button>
      </div>

      <Conversation>
        <ConversationContent className="gap-6">
          {messages.length === 0 ? (
            <div className="mx-auto flex max-w-xl flex-col items-center gap-5 py-10 text-center">
              <div className="bg-primary/10 text-primary flex size-12 items-center justify-center rounded-full">
                <Headset className="size-6" />
              </div>
              <div className="space-y-1.5">
                <h2 className="text-lg font-semibold">
                  Hi! I&apos;m the Lakeside AI Hub assistant.
                </h2>
                <p className="text-muted-foreground text-sm">
                  Ask about our services, prices or how to get started, in
                  English or Finnish. I answer from the hub&apos;s own catalogue
                  and can pass your question to a person.
                </p>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                {STARTERS.map((s) => (
                  <Button
                    key={s}
                    variant="outline"
                    size="sm"
                    className="h-auto py-1.5 text-left font-normal whitespace-normal"
                    onClick={() => send(s)}
                  >
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <Message key={message.id} from={message.role}>
                <MessageContent className="w-full">
                  {message.role === "user" ? (
                    message.parts.map((p, i) =>
                      p.type === "text" ? (
                        <span key={i} className="whitespace-pre-wrap">
                          {p.text}
                        </span>
                      ) : null,
                    )
                  ) : (
                    <AssistantMessage
                      message={message}
                      onApproval={addToolApprovalResponse}
                    />
                  )}
                </MessageContent>
              </Message>
            ))
          )}
          {waiting && <Shimmer className="text-sm">Looking it up…</Shimmer>}
          {error && (
            <p className="text-destructive text-sm" role="alert">
              {errorText(error)}
            </p>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <div className="border-t p-3">
        <PromptInput onSubmit={({ text }) => send(text)}>
          <PromptInputBody>
            <PromptInputTextarea
              value={input}
              onChange={(e) => setInput(e.currentTarget.value)}
              placeholder="Ask the helpdesk…"
              maxLength={2000}
            />
          </PromptInputBody>
          <PromptInputFooter className="justify-between">
            <span className="text-muted-foreground px-2 text-xs">
              AI assistant · answers can contain mistakes
            </span>
            <PromptInputSubmit
              status={status}
              onStop={stop}
              disabled={!busy && !input.trim()}
            />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}
