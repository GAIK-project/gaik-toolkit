"use client";

// "How does the helpdesk chatbot work?": a flowchart, three illustrated steps,
// and what a real deployment uses in place of the demo's in-memory search.

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { CircleHelp } from "lucide-react";
import Image from "next/image";

const STEPS = [
  {
    image: "/helpdesk-chatbot/step-ask.webp",
    title: "You ask",
    text: "In your own words, in Finnish or English. The model reads the question and the conversation so far.",
  },
  {
    image: "/helpdesk-chatbot/step-search.webp",
    title: "It looks it up",
    text: "The model chooses a tool: the service catalogue, the FAQ, or both. It may only state what a tool returned.",
  },
  {
    image: "/helpdesk-chatbot/step-answer.webp",
    title: "It answers, or passes it on",
    text: "You see which entries it used. When it cannot help, it offers to send the question to the right team, after you approve.",
  },
];

function Box({
  x,
  y,
  w,
  title,
  sub,
  accent,
}: {
  x: number;
  y: number;
  w: number;
  title: string;
  sub: string;
  accent?: boolean;
}) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height="52"
        rx="8"
        className={
          accent ? "fill-primary/10 stroke-primary" : "fill-card stroke-border"
        }
      />
      <text
        x={x + w / 2}
        y={y + 22}
        textAnchor="middle"
        className="text-[12px] font-semibold"
        fill="currentColor"
      >
        {title}
      </text>
      <text
        x={x + w / 2}
        y={y + 39}
        textAnchor="middle"
        className="fill-muted-foreground text-[10.5px]"
      >
        {sub}
      </text>
    </g>
  );
}

/** Question → model → tools → answer, with the approval gate on the hand-off. */
function Flowchart() {
  const arrow = "stroke-muted-foreground";
  return (
    <svg
      viewBox="0 0 640 230"
      role="img"
      aria-label="The question goes to the AI model, which searches the service catalogue and the FAQ, or asks your approval to pass it to a person, and then answers with its sources."
      className="text-foreground h-auto w-full"
    >
      <defs>
        <marker
          id="helpdesk-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path d="M0 0 L10 5 L0 10 z" className="fill-muted-foreground" />
        </marker>
      </defs>

      <Box x={8} y={89} w={112} title="Your question" sub="any language" />
      <Box x={160} y={89} w={124} title="AI model" sub="picks a tool" accent />
      <Box
        x={330}
        y={14}
        w={150}
        title="Service catalogue"
        sub="filters + ranking"
      />
      <Box x={330} y={89} w={150} title="FAQ articles" sub="keyword search" />
      <Box
        x={330}
        y={164}
        w={150}
        title="Hand-off to a person"
        sub="asks you first"
      />
      <Box
        x={520}
        y={89}
        w={112}
        title="Answer"
        sub="with its sources"
        accent
      />

      <path
        d="M120 115 H156"
        className={arrow}
        fill="none"
        markerEnd="url(#helpdesk-arrow)"
      />
      {[40, 115, 190].map((y) => (
        <path
          key={y}
          d={`M284 115 C306 115 304 ${y} 326 ${y}`}
          className={arrow}
          fill="none"
          markerEnd="url(#helpdesk-arrow)"
        />
      ))}
      {[40, 115].map((y) => (
        <path
          key={y}
          d={`M480 ${y} C500 ${y} 498 115 516 115`}
          className={arrow}
          fill="none"
          markerEnd="url(#helpdesk-arrow)"
        />
      ))}
      <path
        d="M480 190 C500 190 498 115 516 115"
        className="stroke-primary"
        strokeDasharray="4 3"
        fill="none"
        markerEnd="url(#helpdesk-arrow)"
      />
      <text
        x="222"
        y="72"
        textAnchor="middle"
        className="fill-muted-foreground text-[10px]"
      >
        loops until it has enough
      </text>
      <path
        d="M196 89 C196 70 248 70 248 86"
        className={arrow}
        fill="none"
        markerEnd="url(#helpdesk-arrow)"
      />
    </svg>
  );
}

export function HowItWorks() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <CircleHelp className="size-4" />
          How it works
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>How the helpdesk chatbot works</DialogTitle>
          <DialogDescription>
            An AI model that answers only from the organisation&apos;s own
            knowledge, and hands over to a person when it should.
          </DialogDescription>
        </DialogHeader>

        <ol className="grid gap-4 sm:grid-cols-3">
          {STEPS.map((step, i) => (
            <li key={step.title} className="space-y-2">
              <div className="bg-muted/40 overflow-hidden rounded-lg border">
                <Image
                  src={step.image}
                  alt=""
                  width={512}
                  height={512}
                  className="aspect-[4/3] w-full object-cover"
                />
              </div>
              <p className="text-sm font-semibold">
                {i + 1}. {step.title}
              </p>
              <p className="text-muted-foreground text-sm">{step.text}</p>
            </li>
          ))}
        </ol>

        <div className="rounded-lg border p-3">
          <Flowchart />
        </div>

        <div className="space-y-2 text-sm">
          <p className="font-medium">Built with</p>
          <ul className="text-muted-foreground list-disc space-y-1 pl-5">
            <li>
              AI SDK 7 agent with three tools on Azure OpenAI. The hand-off tool
              needs your approval before it runs.
            </li>
            <li>
              Here the knowledge is a small fictional catalogue searched in
              memory. A real deployment keeps it in PostgreSQL and searches it
              with SQL full-text search, or semantically with pgvector, the same
              retrieval the GAIK RAG Builder uses.
            </li>
            <li>
              Based on the{" "}
              <a
                href="https://helpdesk.2.rahtiapp.fi/"
                target="_blank"
                rel="noreferrer"
                className="text-primary underline-offset-4 hover:underline"
              >
                FAIR Helpdesk
              </a>
              , which runs the same pattern in production with an admin view for
              tickets and content.
            </li>
          </ul>
        </div>
      </DialogContent>
    </Dialog>
  );
}
