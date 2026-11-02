"use client";

import { SectionGuide } from "@/components/demo/section-guide";
import { Card, CardContent, CardDescription } from "@/components/ui/card";
import {
  HELPDESK_EXAMPLES,
  getHelpdeskExample,
} from "@/lib/helpdesk-chatbot/examples";
import { cn } from "@/lib/utils";
import { Building2, Laptop, Wand2, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { HelpdeskChat } from "./helpdesk-chat";

const ICONS: Record<string, LucideIcon> = {
  "ai-hub": Building2,
  "it-hr": Laptop,
};

const STEPS = [
  {
    title: "Pick a helpdesk",
    text: "Two organisations, each with its own services and FAQ.",
  },
  {
    title: "Ask a question",
    text: "Use a starter question or write your own, in English or Finnish.",
  },
  {
    title: "See where it comes from",
    text: "Under each answer: the knowledge it used and the FAQ articles to open.",
  },
  {
    title: "Hand over to a person",
    text: "When a person is needed, the assistant asks first, then opens a contact form.",
  },
];

const NOTES = [
  "Answers come only from the helpdesk's own services and FAQ. Ask about something outside them and the assistant says so.",
  "Watch a demo conversation plays a scripted chat without calling the AI. Nothing is sent from any contact form.",
];

/** Ready-made helpdesks: pick one, ask it questions, see its sources. */
export function HelpdeskExampleSection({ onCreate }: { onCreate: () => void }) {
  const [selectedId, setSelectedId] = useState(HELPDESK_EXAMPLES[0].id);
  const example = getHelpdeskExample(selectedId) ?? HELPDESK_EXAMPLES[0];

  return (
    <div className="space-y-6">
      <SectionGuide
        heading="How to try the example"
        steps={STEPS}
        notes={NOTES}
      />

      <Card>
        <CardContent className="space-y-6 pt-6">
          <CardDescription>
            A helpdesk assistant answers from an organisation&apos;s own
            services and FAQ, names its sources, and passes the question to a
            person when it cannot answer. Pick a helpdesk to try.
          </CardDescription>

          <div
            role="radiogroup"
            aria-label="Example helpdesk"
            className="grid gap-3 sm:grid-cols-2"
          >
            {HELPDESK_EXAMPLES.map((item) => {
              const Icon = ICONS[item.id] ?? Building2;
              const selected = item.id === example.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setSelectedId(item.id)}
                  className={cn(
                    "flex items-start gap-3 rounded-xl border-2 p-4 text-left transition-all",
                    selected
                      ? "border-primary bg-primary/5"
                      : "bg-card hover:border-primary/40",
                  )}
                >
                  <span className="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg">
                    <Icon className="size-5" />
                  </span>
                  <span className="min-w-0">
                    <span className="block font-semibold">{item.title}</span>
                    <span className="text-muted-foreground block text-sm">
                      {item.summary}
                    </span>
                    <span className="mt-2 flex flex-wrap gap-1.5">
                      {item.tags.map((tag) => (
                        <span
                          key={tag}
                          className="border-border/70 bg-muted/40 text-muted-foreground rounded-full border px-2 py-0.5 text-xs"
                        >
                          {tag}
                        </span>
                      ))}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>

          {/* A new key gives each helpdesk a fresh conversation. */}
          <HelpdeskChat key={example.id} example={example} />

          <div className="flex flex-wrap items-center gap-4 border-t pt-4">
            <button
              type="button"
              onClick={onCreate}
              className="text-primary flex items-center gap-2 text-sm font-medium hover:underline"
            >
              <Wand2 className="size-4" />
              Want your own FAQ and services? Test on your own data
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
