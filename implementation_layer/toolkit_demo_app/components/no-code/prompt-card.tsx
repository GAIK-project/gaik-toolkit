"use client";

import { Button } from "@/components/ui/button";
import { chatApps, type Prompt } from "@/lib/no-code/catalog";
import { cn } from "@/lib/utils";
import { ExternalLink } from "lucide-react";
import { useId, useState } from "react";
import { CopyAndOpen, CopyButton } from "./actions";
import { ClaudeIcon, OpenAIIcon } from "./provider-icons";

export function PromptCard({ prompt }: { prompt: Prompt }) {
  const [index, setIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const previewId = useId();
  const variant = prompt.variants[index];
  const next = prompt.then.charAt(0).toLowerCase() + prompt.then.slice(1);
  const message = `Prompt copied. Paste it, then ${next}`;

  return (
    <article className="bg-card flex flex-col gap-4 rounded-xl border p-5">
      <header className="space-y-1">
        <h3 className="text-lg font-semibold">{prompt.title}</h3>
        <p className="text-muted-foreground text-sm">{prompt.tagline}</p>
      </header>

      <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt>Takes</dt>
        <dd className="text-foreground">{prompt.input}</dd>
        <dt>Gives</dt>
        <dd className="text-foreground">{prompt.output}</dd>
      </dl>

      {prompt.variants.length > 1 && (
        <div role="group" aria-label="Prompt version" className="flex gap-1">
          {prompt.variants.map((v, i) => (
            <Button
              key={v.file}
              size="sm"
              variant={i === index ? "secondary" : "ghost"}
              aria-pressed={i === index}
              onClick={() => setIndex(i)}
            >
              {v.label}
            </Button>
          ))}
        </div>
      )}

      <div className="relative">
        <pre
          id={previewId}
          tabIndex={0}
          className={cn(
            "bg-muted/50 overflow-auto rounded-lg p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap",
            expanded ? "max-h-[32rem]" : "max-h-32 overflow-hidden",
          )}
        >
          {variant.text}
        </pre>
        {!expanded && (
          <div className="from-card pointer-events-none absolute inset-x-0 bottom-0 h-12 rounded-b-lg bg-gradient-to-t to-transparent" />
        )}
      </div>
      <Button
        variant="link"
        size="sm"
        className="-mt-2 self-start px-0"
        aria-expanded={expanded}
        aria-controls={previewId}
        onClick={() => setExpanded((e) => !e)}
      >
        {expanded
          ? "Show less"
          : `Show all ${variant.text.length.toLocaleString("en")} characters`}
      </Button>

      <div className="flex flex-wrap gap-2">
        <CopyButton text={variant.text} variant="default" />
        <CopyAndOpen
          text={variant.text}
          href={chatApps.chatgpt}
          message={message}
        >
          <OpenAIIcon />
          Copy and open ChatGPT
        </CopyAndOpen>
        <CopyAndOpen
          text={variant.text}
          href={chatApps.claude}
          message={message}
        >
          <ClaudeIcon />
          Copy and open Claude
        </CopyAndOpen>
      </div>

      <footer className="text-sm">
        <a
          href={prompt.githubUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
        >
          Sample data and guide on GitHub
          <ExternalLink className="size-3.5" />
        </a>
      </footer>
    </article>
  );
}
