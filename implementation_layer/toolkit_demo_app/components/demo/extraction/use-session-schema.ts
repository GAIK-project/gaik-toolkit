"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { useState } from "react";
import toast from "react-hot-toast";

export interface SchemaField {
  name: string;
  type: string;
  description: string;
  required: boolean;
  children?: SchemaField[];
}

interface GeneratedSchema {
  id: string;
  /** The prompt the schema was made from. */
  prompt: string;
  fields: SchemaField[];
}

/** The same normalisation the server applies, so trailing spaces do not make a new prompt. */
export const normalizePrompt = (text: string) =>
  text
    .trim()
    .split("\n")
    .map((line) => line.trimEnd())
    .join("\n");

/**
 * A schema generated for the current prompt. It is kept for the session on the server and
 * is reused by every extraction until the prompt changes or it is generated again.
 */
export function useSessionSchema(prompt: string) {
  const [schema, setSchema] = useState<GeneratedSchema | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  const isCurrent =
    schema !== null && schema.prompt === normalizePrompt(prompt);

  const generate = async () => {
    setIsGenerating(true);
    try {
      const form = new FormData();
      form.append("user_requirements", prompt);
      const response = await apiFetch("/api/pipeline/schema", {
        method: "POST",
        body: form,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "The schema could not be generated");
      }
      const body = (await response.json()) as {
        schema_id: string;
        fields: SchemaField[];
      };
      setSchema({
        id: body.schema_id,
        prompt: normalizePrompt(prompt),
        fields: body.fields,
      });
      toast.success("Schema generated");
    } catch (error) {
      if (error instanceof RateLimitError) return; // The toast is already shown.
      toast.error(
        error instanceof Error ? error.message : "The schema failed to load",
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const clear = () => setSchema(null);

  return {
    schema,
    /** True when the schema was made from exactly the current prompt. */
    isCurrent,
    isGenerating,
    generate,
    clear,
  };
}
