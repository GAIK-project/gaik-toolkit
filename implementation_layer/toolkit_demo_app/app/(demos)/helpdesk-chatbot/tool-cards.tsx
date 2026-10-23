"use client";

// How each tool call shows up in the chat, after the FAIR Helpdesk: a quiet
// shimmer while it runs, a collapsed list of service rows that open into
// details, and the hand-off as an approval card followed by a contact form.

import { Shimmer } from "@/components/ai-elements/shimmer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { HelpdeskUIMessage } from "@/lib/helpdesk-chatbot/agent";
import { TEAMS } from "@/lib/helpdesk-chatbot/knowledge";
import { cn } from "@/lib/utils";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Loader2,
  Send,
  UserPlus,
  X,
} from "lucide-react";
import { motion } from "motion/react";
import dynamic from "next/dynamic";
import { type ReactNode, useEffect, useState } from "react";

const SuccessAnimation = dynamic(
  () =>
    import("@/app/(auth)/components/success-animation").then(
      (mod) => mod.SuccessAnimation,
    ),
  { ssr: false },
);

type Part<T extends string> = Extract<
  HelpdeskUIMessage["parts"][number],
  { type: T }
>;
type Service = Extract<
  Part<"tool-searchServices">,
  { state: "output-available" }
>["output"]["services"][number];

export function isToolRunning(state: string | undefined): boolean {
  return state === "input-streaming" || state === "input-available";
}

export function ToolShimmer({ children }: { children: string }) {
  return (
    <div className="py-2">
      <Shimmer className="text-muted-foreground text-sm">{children}</Shimmer>
    </div>
  );
}

function ToolCollapsible({
  label,
  defaultOpen = false,
  children,
}: {
  label: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="py-1.5">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="text-muted-foreground hover:text-foreground flex cursor-pointer items-center gap-1.5 text-xs transition-colors"
      >
        <ChevronDown
          className={cn(
            "size-3.5 transition-transform duration-200",
            !open && "-rotate-90",
          )}
        />
        {label}
      </button>
      {open && <div className="pt-1">{children}</div>}
    </div>
  );
}

const CATEGORY_LABELS: Record<string, string> = {
  advisory: "Advisory",
  "proof-of-concept": "Proof-of-concept",
  training: "Training",
  funding: "Funding",
  "technology-testing": "Technology testing",
};

const META_BADGE =
  "border-border bg-muted/50 text-muted-foreground text-[10px] whitespace-nowrap";

function ServiceRow({
  service,
  onSelect,
}: {
  service: Service;
  onSelect: (s: Service) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(service)}
      className="group/row border-border/60 bg-card hover:border-primary/40 hover:bg-primary/10 w-full cursor-pointer rounded-lg border px-2.5 py-2 text-left transition-all duration-150 hover:shadow-sm active:scale-[0.99]"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-foreground group-hover/row:text-primary truncate text-sm font-medium">
          {service.name}
        </span>
        <ChevronRight className="text-muted-foreground/50 group-hover/row:text-primary/70 size-3.5 shrink-0 transition-colors" />
      </div>
      <p className="text-foreground/50 mt-0.5 truncate text-xs">
        {service.summary}
      </p>
      <div className="text-foreground/60 mt-1 flex items-center gap-1.5 text-xs">
        <span className="truncate">{service.price}</span>
        <Badge variant="outline" className={META_BADGE}>
          {CATEGORY_LABELS[service.category] ?? service.category}
        </Badge>
      </div>
    </button>
  );
}

function ServiceDetail({ service }: { service: Service }) {
  const facts = [
    ["Price", service.price],
    ["Duration", service.duration],
    ["Handled by", service.team],
    ["Category", CATEGORY_LABELS[service.category] ?? service.category],
  ];
  return (
    <div className="space-y-4 text-sm">
      <p>{service.summary}</p>
      <p className="text-muted-foreground">{service.details}</p>
      <dl className="grid grid-cols-2 gap-3 rounded-lg border p-3">
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt className="text-muted-foreground text-xs">{label}</dt>
            <dd className="font-medium">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

const PREVIEW_COUNT = 4;

export function ServiceList({
  part,
  defaultOpen,
}: {
  part: Part<"tool-searchServices">;
  defaultOpen?: boolean;
}) {
  const [selected, setSelected] = useState<Service | null>(null);
  const [showAll, setShowAll] = useState(false);

  if (isToolRunning(part.state))
    return <ToolShimmer>Searching the service catalogue…</ToolShimmer>;
  if (part.state !== "output-available") return null;

  const { services } = part.output;
  if (services.length === 0) return null;
  const count = `${services.length} ${services.length === 1 ? "service" : "services"} found`;
  const hidden = services.length - PREVIEW_COUNT;

  return (
    <>
      <ToolCollapsible label={count} defaultOpen={defaultOpen}>
        <div className="flex flex-col gap-1 py-1">
          {services.slice(0, PREVIEW_COUNT).map((s) => (
            <ServiceRow key={s.id} service={s} onSelect={setSelected} />
          ))}
          {hidden > 0 && (
            <button
              type="button"
              onClick={() => setShowAll(true)}
              className="text-primary hover:text-primary/80 self-start pt-0.5 text-xs transition-colors hover:underline"
            >
              See {hidden} more
            </button>
          )}
        </div>
      </ToolCollapsible>

      <Dialog open={showAll} onOpenChange={setShowAll}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>All {services.length} services</DialogTitle>
            <DialogDescription className="sr-only">
              Every service that matched
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {services.map((s) => (
              <ServiceRow
                key={s.id}
                service={s}
                onSelect={(next) => {
                  setShowAll(false);
                  setSelected(next);
                }}
              />
            ))}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={selected !== null}
        onOpenChange={(open) => !open && setSelected(null)}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{selected?.name}</DialogTitle>
            <DialogDescription className="sr-only">
              Service details
            </DialogDescription>
          </DialogHeader>
          {selected && <ServiceDetail service={selected} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

// ---------------------------------------------------------------------------
// Hand-off: approval card → contact form → sent

type ApprovalResponse = { id: string; approved: boolean; reason?: string };

// Without a reason the model only sees "Tool call execution denied" and may
// still talk about a form that never appeared.
const DECLINED_REASON =
  "The user chose not to contact the team, so no form is shown. Acknowledge that briefly and keep helping; do not mention a form.";

const SOFT_SPRING = {
  type: "spring",
  stiffness: 320,
  damping: 30,
  mass: 0.7,
} as const;

const INPUT_CLASS =
  "border-input bg-background focus-visible:ring-ring w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none";

function ApprovalCard({
  part,
  onApproval,
  demo,
}: {
  part: Extract<
    Part<"tool-requestHumanHandoff">,
    { state: "approval-requested" }
  >;
  onApproval: (response: ApprovalResponse) => void;
  /** Demo playback: point at the button the script is about to press. */
  demo?: boolean;
}) {
  const [answered, setAnswered] = useState(false);
  const respond = (approved: boolean) => {
    setAnswered(true);
    onApproval({
      id: part.approval.id,
      approved,
      reason: approved ? undefined : DECLINED_REASON,
    });
  };
  const team = TEAMS[part.input.team];

  return (
    <div className="border-border/60 from-card via-card to-primary/[0.03] relative overflow-hidden rounded-xl border bg-gradient-to-br p-4 shadow-[0_1px_0_0_rgb(0_0_0_/_0.02),_0_8px_24px_-12px_rgb(0_0_0_/_0.08)]">
      <motion.span
        aria-hidden
        className="via-primary/50 pointer-events-none absolute inset-x-4 top-0 h-px origin-left bg-gradient-to-r from-transparent to-transparent"
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ delay: 0.05, duration: 0.45, ease: "easeOut" }}
      />
      <div className="flex items-start gap-3">
        <motion.div
          initial={{ scale: 0.55, opacity: 0, rotate: -8 }}
          animate={{ scale: 1, opacity: 1, rotate: 0 }}
          transition={{ ...SOFT_SPRING, delay: 0.05 }}
          className="bg-primary/10 text-primary ring-primary/15 grid size-9 shrink-0 place-items-center rounded-lg ring-1 ring-inset"
        >
          <UserPlus className="size-[18px]" />
        </motion.div>
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm leading-snug font-medium">
            Contact the {team.name}?
          </p>
          <p className="text-muted-foreground text-xs leading-relaxed">
            A person from the team can help with this. Opening the contact form
            sends nothing yet.
          </p>
          <p className="text-muted-foreground text-xs leading-relaxed">
            Topic:{" "}
            <span className="text-foreground font-medium">
              {part.input.topic}
            </span>
          </p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <motion.button
          type="button"
          disabled={answered}
          whileHover={{ y: -1 }}
          whileTap={{ scale: 0.97 }}
          transition={SOFT_SPRING}
          onClick={() => respond(true)}
          className={cn(
            demo && "ring-primary/40 animate-pulse ring-4",
            "bg-primary text-primary-foreground ring-primary/20 hover:bg-primary/90 focus-visible:ring-ring inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-semibold shadow-sm ring-1 transition-colors ring-inset focus-visible:ring-2 focus-visible:outline-none disabled:opacity-60",
          )}
        >
          <Check className="size-3.5" strokeWidth={2.5} aria-hidden />
          Open the contact form
        </motion.button>
        <motion.button
          type="button"
          disabled={answered}
          whileHover={{ y: -1 }}
          whileTap={{ scale: 0.97 }}
          transition={SOFT_SPRING}
          onClick={() => respond(false)}
          className="border-border bg-background/60 text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:opacity-60"
        >
          Not now
        </motion.button>
      </div>
    </div>
  );
}

export type DemoFill = { name: string; email: string };

function ContactForm({
  output,
  demoFill,
}: {
  output: Extract<
    Part<"tool-requestHumanHandoff">,
    { state: "output-available" }
  >["output"];
  /** Demo playback: type these in and send, as a visitor would. */
  demoFill?: DemoFill | null;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState(output.summary);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (!demoFill) return;
    let cancelled = false;
    const timers: ReturnType<typeof setTimeout>[] = [];
    const at = (ms: number, fn: () => void) =>
      timers.push(setTimeout(() => !cancelled && fn(), ms));
    let t = 0;
    for (let i = 1; i <= demoFill.name.length; i++)
      at((t += 45), () => setName(demoFill.name.slice(0, i)));
    for (let i = 1; i <= demoFill.email.length; i++)
      at((t += 40), () => setEmail(demoFill.email.slice(0, i)));
    at(t + 900, () => setSent(true));
    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  }, [demoFill]);

  if (sent)
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3 }}
        className="flex flex-col items-center rounded-lg border border-green-200 bg-green-50 p-5 dark:border-green-800 dark:bg-green-950/30"
        aria-live="polite"
      >
        <SuccessAnimation />
        <div className="space-y-1.5 text-center">
          <h4 className="text-sm font-medium text-green-700 dark:text-green-400">
            Request {output.ticketId} sent to the {output.team}
          </h4>
          <p className="text-muted-foreground text-xs">
            They reply to {email} within {output.responseTime}.
          </p>
          <p className="text-muted-foreground text-xs">
            Demo: nothing was actually sent.
          </p>
        </div>
      </motion.div>
    );

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={SOFT_SPRING}
      className="border-border bg-card space-y-3 rounded-lg border p-4"
    >
      <div className="flex items-center gap-2 text-sm font-medium">
        <UserPlus className="text-primary size-[18px]" />
        Contact the {output.team}
      </div>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          setSent(true);
        }}
      >
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label
              htmlFor="handoff-name"
              className="text-foreground/80 text-xs font-medium"
            >
              Name
            </label>
            <input
              id="handoff-name"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={cn(INPUT_CLASS, "h-8")}
            />
          </div>
          <div className="space-y-1.5">
            <label
              htmlFor="handoff-email"
              className="text-foreground/80 text-xs font-medium"
            >
              Email
            </label>
            <input
              id="handoff-email"
              type="email"
              autoComplete="email"
              spellCheck={false}
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={cn(INPUT_CLASS, "h-8")}
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <label
            htmlFor="handoff-message"
            className="text-foreground/80 text-xs font-medium"
          >
            What do you need help with?
          </label>
          <textarea
            id="handoff-message"
            rows={3}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            className={cn(INPUT_CLASS, "resize-none py-2")}
          />
        </div>
        <Button
          type="submit"
          size="sm"
          className="w-full gap-1.5"
          disabled={!name.trim() || !email.trim() || !message.trim()}
        >
          <Send className="size-3.5" />
          Send request
        </Button>
      </form>
      <p className="text-muted-foreground text-xs">
        The assistant wrote the message from your conversation; edit it before
        sending. This is a demo: nothing leaves your browser.
      </p>
    </motion.div>
  );
}

export function HandoffCard({
  part,
  onApproval,
  demoFill,
  demo,
}: {
  part: Part<"tool-requestHumanHandoff">;
  onApproval: (response: ApprovalResponse) => void;
  demoFill?: DemoFill | null;
  demo?: boolean;
}) {
  // A plain keyed motion.div per state: an exit animation between states can
  // deadlock when v7 moves input-available → approval-requested.
  let key: string;
  let node: ReactNode;
  switch (part.state) {
    case "input-streaming":
    case "input-available":
      key = "loading";
      node = <ToolShimmer>Preparing a contact request…</ToolShimmer>;
      break;
    case "approval-requested":
      key = "approval";
      node = <ApprovalCard part={part} onApproval={onApproval} demo={demo} />;
      break;
    case "approval-responded":
      key = "responded";
      node = (
        <div className="text-muted-foreground flex items-center gap-2 py-2">
          <Loader2 className="size-3.5 animate-spin" />
          <Shimmer className="text-sm">Opening the contact form…</Shimmer>
        </div>
      );
      break;
    case "output-available":
      key = "form";
      node = <ContactForm output={part.output} demoFill={demoFill} />;
      break;
    case "output-denied":
      key = "denied";
      node = (
        <div className="border-border/60 bg-muted/40 text-muted-foreground inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs">
          <X className="size-3" strokeWidth={2.5} aria-hidden />
          Contact request cancelled
        </div>
      );
      break;
    default:
      key = "error";
      node = (
        <p className="text-destructive py-2 text-sm">
          The contact form could not be opened.
        </p>
      );
  }
  return (
    <motion.div
      key={key}
      className="py-1.5"
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      {node}
    </motion.div>
  );
}
