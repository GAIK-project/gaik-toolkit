import { NoCodeHeader } from "@/components/no-code/no-code-header";
import { PromptCard } from "@/components/no-code/prompt-card";
import { prompts } from "@/lib/no-code/catalog";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Prompts",
  description:
    "Open a GAIK prompt in ChatGPT or Claude to extract structured data from transcripts and documents.",
};

export default function PromptsPage() {
  return (
    <div className="space-y-10">
      <NoCodeHeader active="/prompts" />
      <div className="grid items-start gap-5 md:grid-cols-2">
        {prompts.map((prompt) => (
          <PromptCard key={prompt.id} prompt={prompt} />
        ))}
      </div>
    </div>
  );
}
