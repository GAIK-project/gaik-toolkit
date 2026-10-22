"use client";

// "How does Trace sources work?": a help button that opens a diagram and three steps.

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

const STEPS = [
  "The model reads the document and returns, for every value, the page and the exact text it read it from. It never gives coordinates.",
  "Plain code looks for that text in the PDF's own text layer. Case, spacing and punctuation are ignored; nothing is matched loosely.",
  "The PDF stores where every word is, so the words that matched give the box. The value must also be inside its quote.",
];

/** A PDF page, the model's answer and the check, with arrows between them. */
function Diagram() {
  const mono = "font-mono";
  return (
    <svg
      viewBox="0 0 640 262"
      role="img"
      aria-label="The model returns a value with its quote; code finds the quote in the PDF and draws the box from the matched words."
      className="text-foreground h-auto w-full"
    >
      <defs>
        <marker
          id="trace-arrow"
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

      {/* The PDF page */}
      <rect
        x="16"
        y="14"
        width="208"
        height="234"
        rx="6"
        className="fill-card stroke-border"
      />
      <text x="30" y="36" className="fill-muted-foreground text-[11px]">
        invoice.pdf, page 1
      </text>
      {[56, 70, 84, 112, 126].map((y) => (
        <rect
          key={y}
          x="30"
          y={y}
          width={y % 28 ? 150 : 110}
          height="6"
          rx="3"
          className="fill-muted"
        />
      ))}
      <rect
        x="26"
        y="150"
        width="161"
        height="22"
        rx="3"
        className="fill-amber-300/40 stroke-amber-500"
      />
      {/* Seven units per character (textLength below), so the value's box lines up. */}
      <rect
        x="78"
        y="153"
        width="60"
        height="16"
        rx="2"
        className="stroke-primary fill-none"
        strokeWidth="2"
      />
      <text
        x="32"
        y="165"
        textLength="133"
        lengthAdjust="spacingAndGlyphs"
        className={`${mono} text-[11px]`}
        fill="currentColor"
      >
        Total: 1.234,50 EUR
      </text>
      {[190, 204, 218].map((y) => (
        <rect
          key={y}
          x="30"
          y={y}
          width={y === 204 ? 90 : 140}
          height="6"
          rx="3"
          className="fill-muted"
        />
      ))}

      {/* 1: what the model returns */}
      <rect
        x="300"
        y="14"
        width="324"
        height="104"
        rx="6"
        className="fill-card stroke-border"
      />
      <circle cx="318" cy="34" r="9" className="fill-primary" />
      <text
        x="318"
        y="38"
        textAnchor="middle"
        className="fill-primary-foreground text-[11px] font-semibold"
      >
        1
      </text>
      <text
        x="334"
        y="38"
        className="text-[12px] font-semibold"
        fill="currentColor"
      >
        The model returns the value and its quote
      </text>
      <text className={`${mono} fill-muted-foreground text-[11px]`}>
        <tspan x="318" y="62">
          {'"total": 1234.5,'}
        </tspan>
        <tspan x="318" y="80">
          {'"page": 1,'}
        </tspan>
        <tspan x="318" y="98">
          {'"quote": "Total: 1.234,50 EUR"'}
        </tspan>
      </text>

      {/* 2: the check */}
      <rect
        x="300"
        y="144"
        width="324"
        height="104"
        rx="6"
        className="fill-card stroke-border"
      />
      <circle cx="318" cy="164" r="9" className="fill-primary" />
      <text
        x="318"
        y="168"
        textAnchor="middle"
        className="fill-primary-foreground text-[11px] font-semibold"
      >
        2
      </text>
      <text
        x="334"
        y="168"
        className="text-[12px] font-semibold"
        fill="currentColor"
      >
        Code finds the quote in the PDF
      </text>
      <text className="fill-muted-foreground text-[11px]">
        <tspan x="318" y="192">
          The words Total, 1.234,50 and EUR are in
        </tspan>
        <tspan x="318" y="208">
          the text layer, with their place on the page.
        </tspan>
        <tspan x="318" y="230">
          1234.5 is inside the quote, so it is verified.
        </tspan>
      </text>

      {/* Arrows */}
      <path
        d="M224 66 H296"
        className="stroke-muted-foreground"
        fill="none"
        markerEnd="url(#trace-arrow)"
      />
      <text
        x="260"
        y="58"
        textAnchor="middle"
        className="fill-muted-foreground text-[10px]"
      >
        reads
      </text>
      <path
        d="M462 118 V140"
        className="stroke-muted-foreground"
        fill="none"
        markerEnd="url(#trace-arrow)"
      />
      <path
        d="M300 196 H246 Q238 196 238 188 V170 Q238 161 230 161 H197"
        className="stroke-primary"
        fill="none"
        strokeWidth="1.5"
        markerEnd="url(#trace-arrow)"
      />
      <text
        x="268"
        y="212"
        textAnchor="middle"
        className="fill-primary text-[10px] font-medium"
      >
        the box
      </text>
    </svg>
  );
}

/** A "?" button that explains how Trace sources finds and checks a quote. */
export function TraceExplainer({ label }: { label?: string }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        {label ? (
          <Button variant="link" size="sm" className="h-auto p-0 text-sm">
            {label}
          </Button>
        ) : (
          <button
            type="button"
            aria-label="How Trace sources works"
            title="How Trace sources works"
            className="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-flex rounded-full focus-visible:ring-2 focus-visible:outline-none"
          >
            <CircleHelp className="size-4" />
          </button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>How Trace sources works</DialogTitle>
          <DialogDescription>
            The model says what it read. The PDF says where it is.
          </DialogDescription>
        </DialogHeader>
        <Diagram />
        <ol className="list-decimal space-y-1.5 pl-5 text-sm">
          {STEPS.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        <p className="text-muted-foreground text-sm">
          Flagged for a person: a quote that is not in the PDF, or one that does
          not hold its value. Images have no text layer, so their quotes cannot
          be checked.
        </p>
      </DialogContent>
    </Dialog>
  );
}
