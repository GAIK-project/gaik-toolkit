"use client";

// How each tool call shows up in the chat: what the bot looked at, and the
// hand-off request the user approves.

import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { HelpdeskUIMessage } from "@/lib/helpdesk-chatbot/agent";
import { TEAMS } from "@/lib/helpdesk-chatbot/knowledge";
import { cn } from "@/lib/utils";
import {
  BookOpen,
  Check,
  ChevronDown,
  LayoutGrid,
  Loader2,
  UserRound,
  X,
} from "lucide-react";
import { useState } from "react";

type Part<T extends string> = Extract<
  HelpdeskUIMessage["parts"][number],
  { type: T }
>;

function Pending({ children }: { children: string }) {
  return (
    <p className="text-muted-foreground flex items-center gap-2 text-xs">
      <Loader2 className="size-3.5 animate-spin" />
      {children}
    </p>
  );
}

function Trigger({
  icon: Icon,
  children,
}: {
  icon: typeof BookOpen;
  children: string;
}) {
  return (
    <CollapsibleTrigger className="text-muted-foreground hover:text-foreground group flex items-center gap-1.5 text-xs">
      <Icon className="size-3.5" />
      {children}
      <ChevronDown className="size-3.5 transition-transform group-data-[state=open]:rotate-180" />
    </CollapsibleTrigger>
  );
}

export function ServiceList({ part }: { part: Part<"tool-searchServices"> }) {
  if (part.state === "input-streaming" || part.state === "input-available")
    return <Pending>Checking the service catalogue…</Pending>;
  if (part.state !== "output-available") return null;

  const { services } = part.output;
  const filters = [part.input.category, part.input.audience]
    .filter(Boolean)
    .join(", ");
  return (
    <Collapsible>
      <Trigger icon={LayoutGrid}>
        {`Service catalogue${filters ? ` (${filters})` : ""} · ${services.length} ${services.length === 1 ? "service" : "services"}`}
      </Trigger>
      <CollapsibleContent className="mt-2 grid gap-2 sm:grid-cols-2">
        {services.map((s) => (
          <div key={s.id} className="bg-muted/40 rounded-lg border p-3 text-xs">
            <p className="text-foreground text-sm font-medium">{s.name}</p>
            <p className="text-muted-foreground mt-1">{s.summary}</p>
            <p className="mt-2">
              {s.price} · {s.duration}
            </p>
          </div>
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

export function SourceList({ part }: { part: Part<"tool-searchKnowledge"> }) {
  if (part.state === "input-streaming" || part.state === "input-available")
    return <Pending>Searching the FAQ…</Pending>;
  if (part.state !== "output-available") return null;

  const { articles } = part.output;
  if (articles.length === 0)
    return (
      <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
        <BookOpen className="size-3.5" />
        FAQ · nothing matched “{part.input.query}”
      </p>
    );
  return (
    <Collapsible>
      <Trigger icon={BookOpen}>
        {`FAQ · ${articles.map((a) => a.title).join(" · ")}`}
      </Trigger>
      <CollapsibleContent className="mt-2 space-y-2">
        {articles.map((a) => (
          <div key={a.id} className="bg-muted/40 rounded-lg border p-3 text-xs">
            <p className="text-foreground text-sm font-medium">{a.title}</p>
            <p className="text-muted-foreground mt-1">{a.body}</p>
          </div>
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

type ApprovalResponse = { id: string; approved: boolean; reason?: string };

export function HandoffCard({
  part,
  onApproval,
}: {
  part: Part<"tool-requestHumanHandoff">;
  onApproval: (response: ApprovalResponse) => void;
}) {
  const [answered, setAnswered] = useState(false);

  if (part.state === "input-streaming" || part.state === "input-available")
    return <Pending>Preparing a request for the team…</Pending>;

  const team = part.input?.team ? TEAMS[part.input.team] : undefined;
  const frame = "rounded-lg border p-4 text-sm";

  if (part.state === "approval-requested") {
    const respond = (approved: boolean) => {
      setAnswered(true);
      onApproval({
        id: part.approval.id,
        approved,
        // Without a reason the model only sees "Tool call execution denied"
        // and may still talk about a form that never appeared.
        reason: approved
          ? undefined
          : "The user declined. No request was sent; do not ask again.",
      });
    };
    return (
      <div className={cn(frame, "border-primary/40 bg-primary/5")}>
        <p className="flex items-center gap-2 font-medium">
          <UserRound className="text-primary size-4" />
          Pass this to the {team?.name ?? "team"}?
        </p>
        <p className="text-muted-foreground mt-1.5">{part.input.summary}</p>
        <div className="mt-3 flex gap-2">
          <Button size="sm" disabled={answered} onClick={() => respond(true)}>
            Yes, send it
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={answered}
            onClick={() => respond(false)}
          >
            No thanks
          </Button>
        </div>
      </div>
    );
  }

  if (part.state === "approval-responded")
    return <Pending>Sending the request…</Pending>;

  if (part.state === "output-denied")
    return (
      <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
        <X className="size-3.5" />
        Hand-off declined, nothing was sent.
      </p>
    );

  if (part.state === "output-available") {
    const t = part.output;
    return (
      <div className={frame}>
        <p className="flex items-center gap-2 font-medium">
          <Check className="size-4 text-emerald-600" />
          Request {t.ticketId} · {t.team}
        </p>
        <p className="text-muted-foreground mt-1.5">{t.summary}</p>
        <p className="mt-2 text-xs">
          Expected reply within {t.responseTime}.{" "}
          <span className="text-muted-foreground">
            Demo: nothing was actually sent.
          </span>
        </p>
      </div>
    );
  }

  return (
    <p className="text-destructive text-xs">
      The request could not be prepared.
    </p>
  );
}
