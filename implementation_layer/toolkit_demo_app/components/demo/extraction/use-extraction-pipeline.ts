"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { processSSEStream, type SSEStep } from "@/lib/sse";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

export interface ExtractionResult {
  job_id: string;
  raw_transcript?: string | null;
  enhanced_transcript?: string | null;
  /** Set by the text pipeline. */
  input_text?: string | null;
  /** Set by the document (photo or scan) pipeline. */
  parsed_content?: string | null;
  extracted_data: Record<string, unknown>[] | null;
  pdf_available: boolean;
}

export type ExtractionInput =
  | { kind: "text"; text: string }
  | { kind: "audio"; file: File }
  | { kind: "photo"; file: File };

export interface ExtractionRunConfig {
  prompt: string;
  /**
   * A saved schema, used only with the prompt it was made from; the first run makes
   * and saves it. null generates a schema for this run only.
   */
  schemaKey: string | null;
  /** A schema generated for this session from exactly this prompt; wins over the key. */
  schemaId?: string | null;
  enhanced: boolean;
  generatePdf: boolean;
}

/** The text the extraction was made from, whichever input it came from. */
export function sourceTextOf(result: ExtractionResult): string {
  return (
    result.enhanced_transcript ||
    result.raw_transcript ||
    result.input_text ||
    result.parsed_content ||
    ""
  );
}

/** Runs the extraction pipeline of a demo and tracks its steps and result. */
export function useExtractionPipeline(demo: {
  pdfTitle: string;
  demoName: string;
}) {
  const [steps, setSteps] = useState<SSEStep[]>([]);
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [seconds, setSeconds] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const reset = () => {
    abortRef.current?.abort();
    setSteps([]);
    setResult(null);
    setSeconds(null);
    setIsLoading(false);
  };

  const run = async (input: ExtractionInput, config: ExtractionRunConfig) => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    const started = performance.now();
    setIsLoading(true);
    setResult(null);
    setSeconds(null);
    setSteps([]);

    try {
      const form = new FormData();
      form.append("user_requirements", config.prompt);
      form.append("generate_pdf", String(config.generatePdf));
      form.append("pdf_title", demo.pdfTitle);
      if (config.schemaId) {
        form.append("schema_id", config.schemaId);
        form.append("regenerate_schema", "false");
      } else if (config.schemaKey) {
        form.append("schema_key", config.schemaKey);
        form.append("regenerate_schema", "false");
      } else {
        form.append("regenerate_schema", "true");
      }

      let endpoint = "/api/pipeline/text/stream";
      if (input.kind === "text") {
        form.append("text", input.text);
      } else if (input.kind === "audio") {
        endpoint = "/api/pipeline/audio/stream";
        form.append("file", input.file);
        form.append("enhanced", String(config.enhanced));
        form.append("compress_audio", "true");
      } else {
        endpoint = "/api/pipeline/document/stream";
        form.append("file", input.file);
        form.append("parser_type", "vision");
      }

      const response = await apiFetch(endpoint, {
        method: "POST",
        body: form,
        signal: abortRef.current.signal,
      });
      if (!response.ok) throw new Error("Failed to process the report");

      let streamError: Error | null = null;
      await processSSEStream<ExtractionResult>(response, {
        onSteps: (next) => setSteps(next),
        onStepUpdate: (update) =>
          setSteps((previous) =>
            previous.map((step) => (step.step === update.step ? update : step)),
          ),
        onResult: (data) => {
          setResult(data);
          setSeconds((performance.now() - started) / 1000);
          posthog.capture("pipeline_executed", {
            pipeline_type: input.kind,
            demo: demo.demoName,
            saved_schema: Boolean(config.schemaKey),
          });
        },
        onError: (message) => {
          streamError = new Error(message);
        },
      });
      if (streamError) throw streamError;
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return; // The toast is already shown.
      toast.error(error instanceof Error ? error.message : "An error occurred");
      setSteps((previous) =>
        previous.map((step) =>
          step.status === "in_progress"
            ? { ...step, status: "error", message: "Failed" }
            : step,
        ),
      );
    } finally {
      setIsLoading(false);
    }
  };

  return { steps, result, isLoading, seconds, run, reset };
}
