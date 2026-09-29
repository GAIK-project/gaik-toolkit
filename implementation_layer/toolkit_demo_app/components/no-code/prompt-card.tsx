"use client";

import { Button } from "@/components/ui/button";
import { chatApps, type Prompt } from "@/lib/no-code/catalog";
import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { CopyAndOpen, CopyButton } from "./actions";
import { AssetIcon } from "./asset-icon";
import { Disclosure } from "./disclosure";
import { IoLine } from "./io-line";
import { ClaudeIcon, OpenAIIcon } from "./provider-icons";

export function PromptCard({ prompt }: { prompt: Prompt }) {
  const [index, setIndex] = useState(0);
  const variant = prompt.variants[index];

  return (
    <article className="bg-card flex flex-col gap-4 rounded-xl border p-5">
      <header className="flex items-start gap-3">
        <AssetIcon id={prompt.id} />
        <div className="min-w-0 flex-1 space-y-1">
          <h3 className="text-lg leading-tight font-semibold">
            {prompt.title}
          </h3>
          <p className="text-muted-foreground text-sm">{prompt.tagline}</p>
        </div>
        <a
          href={prompt.githubUrl}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`${prompt.title} on GitHub`}
          title="Sample data and guide on GitHub"
          className="text-muted-foreground hover:text-foreground shrink-0 p-1"
        >
          <ExternalLink className="size-4" />
        </a>
      </header>

      <IoLine input={prompt.input} output={prompt.output} />

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

      <div className="flex flex-wrap gap-2">
        <CopyButton text={variant.text} variant="default" />
        <CopyAndOpen
          text={variant.text}
          href={chatApps.chatgpt(variant.text)}
          message={`Sent to ChatGPT. ${prompt.then}`}
        >
          <OpenAIIcon />
          Open in ChatGPT
        </CopyAndOpen>
        <CopyAndOpen
          text={variant.text}
          href={chatApps.claude(variant.text)}
          message={`Prompt copied. If Claude's box is empty, paste it. ${prompt.then}`}
        >
          <ClaudeIcon />
          Open in Claude
        </CopyAndOpen>
      </div>

      <p className="text-muted-foreground -mt-1 text-xs">
        ChatGPT sends it at once. {prompt.then}
      </p>

      <Disclosure label="Read the prompt">
        <pre
          tabIndex={0}
          className="bg-muted/50 max-h-96 overflow-auto rounded-lg p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap"
        >
          {variant.text}
        </pre>
      </Disclosure>
    </article>
  );
}
