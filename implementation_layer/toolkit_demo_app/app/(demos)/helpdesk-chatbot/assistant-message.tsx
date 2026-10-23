"use client";

// One assistant turn, laid out like the FAIR Helpdesk: tool results first, then
// an "Answer" label and the text, then copy/regenerate, and last a "Based on"
// row that says which knowledge the answer drew on and opens the FAQ articles.

import {
  Message,
  MessageAction,
  MessageActions,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { HelpdeskUIMessage } from "@/lib/helpdesk-chatbot/agent";
import { cn } from "@/lib/utils";
import {
  BookOpen,
  Check,
  ChevronDown,
  Copy,
  FileText,
  Lightbulb,
  Loader2,
  RefreshCw,
  Users,
} from "lucide-react";
import { useState } from "react";
import {
  type DemoFill,
  HandoffCard,
  isToolRunning,
  ServiceList,
  ToolShimmer,
} from "./tool-cards";

type Part = HelpdeskUIMessage["parts"][number];
type Article = { id: string; title: string; body: string };

const CHIP =
  "border-border/70 bg-muted/40 inline-flex items-center gap-1 rounded-full border px-2 py-0.5";

type Kind = "catalogue" | "faq" | "team" | "model";
const KINDS: Record<Kind, { label: string; icon: typeof FileText }> = {
  catalogue: { label: "Service catalogue", icon: FileText },
  faq: { label: "FAQ", icon: BookOpen },
  team: { label: "Helpdesk team", icon: Users },
  model: { label: "General knowledge", icon: Lightbulb },
};

/**
 * Which knowledge an answer drew on, read from the tool calls on the message,
 * never from the model's account of itself. No tool at all is shown too, so an
 * ungrounded answer does not look like a grounded one.
 */
function provenance(parts: Part[]): Kind[] {
  const kinds = new Set<Kind>();
  for (const part of parts) {
    if (part.type === "tool-searchServices") kinds.add("catalogue");
    if (
      part.type === "tool-searchKnowledge" &&
      part.state === "output-available" &&
      part.output.articles.length > 0
    )
      kinds.add("faq");
    if (
      part.type === "tool-requestHumanHandoff" &&
      part.state !== "output-denied"
    )
      kinds.add("team");
  }
  return kinds.size ? [...kinds] : ["model"];
}

function articles(parts: Part[]): Article[] {
  const seen = new Map<string, Article>();
  for (const part of parts)
    if (
      part.type === "tool-searchKnowledge" &&
      part.state === "output-available"
    )
      for (const a of part.output.articles) seen.set(a.id, a);
  return [...seen.values()];
}

function textOf(parts: Part[]): string {
  return parts
    .map((p) => (p.type === "text" ? p.text : ""))
    .join("")
    .trim();
}

const ACTION =
  "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground size-7 rounded-full";

export function AssistantMessage({
  message,
  streaming,
  onApproval,
  onRegenerate,
  demoFill,
  demo,
}: {
  message: HelpdeskUIMessage;
  /** This is the last message and the chat is still generating. */
  streaming: boolean;
  onApproval: (response: {
    id: string;
    approved: boolean;
    reason?: string;
  }) => void;
  onRegenerate?: () => void;
  demoFill?: DemoFill | null;
  /** Scripted playback: open lists the presenter would otherwise click. */
  demo?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState<boolean | null>(null);
  const [article, setArticle] = useState<Article | null>(null);

  const text = textOf(message.parts);
  const tools = message.parts.filter((p) => p.type.startsWith("tool-"));
  const toolRunning = tools.some((p) => "state" in p && isToolRunning(p.state));
  const done = !streaming && text.length > 0;
  const sources = articles(message.parts);

  // Untouched, the list is open during demo playback and closed otherwise.
  const showSources = sourcesOpen ?? Boolean(demo);

  return (
    <div className="flex flex-col gap-3">
      <Message from="assistant">
        <MessageContent className="w-full">
          {tools.map((part, i) => {
            const key = `${message.id}-${i}`;
            if (part.type === "tool-searchServices")
              return <ServiceList key={key} part={part} defaultOpen={demo} />;
            if (part.type === "tool-searchKnowledge")
              // Its articles appear in the sources row under the answer.
              return isToolRunning(part.state) ? (
                <ToolShimmer key={key}>Searching the FAQ…</ToolShimmer>
              ) : null;
            if (part.type === "tool-requestHumanHandoff")
              return (
                <HandoffCard
                  key={key}
                  part={part}
                  onApproval={onApproval}
                  demoFill={demoFill}
                  demo={demo}
                />
              );
            return null;
          })}

          {!text && streaming && !toolRunning && (
            <div className="text-muted-foreground py-2">
              <Loader2 className="size-3.5 animate-spin" />
            </div>
          )}

          {text && (
            <>
              <div className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium">
                <BookOpen className="size-4" />
                Answer
              </div>
              <div className={cn(tools.length > 0 && "pt-1")}>
                <MessageResponse>{text}</MessageResponse>
              </div>
            </>
          )}
        </MessageContent>

        {done && (
          <MessageActions className="mt-1 gap-1.5">
            <MessageAction
              tooltip={copied ? "Copied" : "Copy"}
              className={ACTION}
              onClick={() => {
                void navigator.clipboard.writeText(text).then(() => {
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                });
              }}
            >
              {copied ? (
                <Check className="size-4" />
              ) : (
                <Copy className="size-4" />
              )}
            </MessageAction>
            {onRegenerate && (
              <MessageAction
                tooltip="Regenerate"
                className={ACTION}
                onClick={onRegenerate}
              >
                <RefreshCw className="size-4" />
              </MessageAction>
            )}
          </MessageActions>
        )}
      </Message>

      {/* Shown only once the turn is complete, so it cannot flicker between
          sequential tool calls mid-stream. */}
      {done && (
        <Collapsible open={showSources} onOpenChange={setSourcesOpen}>
          <div className="text-muted-foreground flex flex-wrap items-center gap-1.5 text-xs">
            <span className="shrink-0">Based on:</span>
            {provenance(message.parts).map((kind) => {
              const { label, icon: Icon } = KINDS[kind];
              return (
                <span key={kind} className={CHIP}>
                  <Icon className="size-3 shrink-0" aria-hidden />
                  {label}
                </span>
              );
            })}
            {sources.length > 0 && (
              <CollapsibleTrigger
                className={cn(
                  CHIP,
                  "hover:border-border hover:text-foreground cursor-pointer transition-colors",
                )}
              >
                <BookOpen className="size-3 shrink-0" aria-hidden />
                {sources.length} {sources.length === 1 ? "source" : "sources"}
                <ChevronDown
                  className={cn(
                    "size-3 shrink-0 transition-transform duration-200",
                    showSources && "rotate-180",
                  )}
                  aria-hidden
                />
              </CollapsibleTrigger>
            )}
          </div>
          <CollapsibleContent className="mt-2 flex flex-col gap-1.5 pl-1">
            {sources.map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => setArticle(a)}
                className="text-primary flex items-center gap-2 text-left text-xs font-medium hover:underline"
              >
                <BookOpen className="size-3.5 shrink-0" />
                {a.title}
              </button>
            ))}
          </CollapsibleContent>
        </Collapsible>
      )}

      <Dialog
        open={article !== null}
        onOpenChange={(open) => !open && setArticle(null)}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{article?.title}</DialogTitle>
            <DialogDescription>Lakeside AI Hub FAQ</DialogDescription>
          </DialogHeader>
          <p className="text-sm leading-relaxed">{article?.body}</p>
        </DialogContent>
      </Dialog>
    </div>
  );
}
