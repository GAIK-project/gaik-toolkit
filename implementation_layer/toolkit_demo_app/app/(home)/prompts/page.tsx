import { PromptCard } from "@/components/no-code/prompt-card";
import { prompts } from "@/lib/no-code/catalog";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Prompts",
  description:
    "Copy a GAIK prompt into ChatGPT, Claude or any chat assistant to extract structured data from transcripts and documents.",
};

export default function PromptsPage() {
  return (
    <div className="space-y-10">
      <header className="max-w-2xl space-y-3">
        <h1 className="font-serif text-3xl font-semibold tracking-tight md:text-4xl">
          Prompts
        </h1>
        <p className="text-muted-foreground">
          Copy a prompt into ChatGPT, Claude or any chat assistant, then paste
          your transcript or attach your documents. Nothing to install.
        </p>
      </header>
      <div className="grid gap-5 md:grid-cols-2">
        {prompts.map((prompt) => (
          <PromptCard key={prompt.id} prompt={prompt} />
        ))}
      </div>
    </div>
  );
}
