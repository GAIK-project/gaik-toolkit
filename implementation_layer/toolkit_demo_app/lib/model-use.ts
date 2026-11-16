import { pageUsesModelSettings } from "./model-settings";

/** What a demo page sends to a model besides text. */
interface PageNeeds {
  /** "always": every run sends page images. "some": only scans and images do. */
  vision?: "always" | "some";
  /** The page transcribes recordings. */
  speech?: boolean;
  /** The page embeds documents and questions. */
  embeddings?: boolean;
}

const PAGE_NEEDS: Record<string, PageNeeds> = {
  "/vision-extractor": { vision: "always" },
  "/parser": { vision: "some" },
  "/classifier": { vision: "some" },
  "/llm-judge": { vision: "some" },
  "/document-structured": { vision: "some" },
  "/incident-report": { vision: "some", speech: true },
  "/audio-structured": { speech: true },
  "/diary": { speech: true },
  "/rag": { embeddings: true },
  "/transcriber": { speech: true },
};

/** Pages a picked server model runs but an own key does not (api: _SERVER_MODEL_PATHS). */
const SERVER_MODEL_ONLY_PAGES = ["/rag", "/transcriber"];

export const AITTA_SPEECH_MODEL = "Whisper large v3";
export const AITTA_EMBEDDING_MODEL = "multilingual-e5-large";

export interface ActiveModel {
  /** A key the user entered, or a model of the server. */
  own: boolean;
  provider: string;
  /** The model ID or deployment name. */
  model: string;
  label: string;
  /** False for a text-only model. Unknown for an own key: taken as true. */
  vision: boolean;
  /** False when the provider has no speech-to-text. */
  audio: boolean;
  /** The server's own default: what runs when nothing is picked. */
  isDefault: boolean;
}

export interface ModelUse {
  /** The active model runs this page's requests. */
  runsHere: boolean;
  /** One sentence for the menu and the page. */
  summary: string;
  /** What else takes part: the speech or embedding model. */
  details: string[];
  /** Set when a run would fail or leave part of the input unread. */
  problem: string | null;
}

/** Aitta model IDs an own key can name that do not read images (api: _AITTA_TEXT_ONLY). */
const AITTA_TEXT_ONLY = [
  "openai/gpt-oss-",
  "qwen/qwen3-coder",
  "qwen/qwen-agentworld",
  "swiss-ai/apertus",
  "allenai/olmo",
  "lumiopen/",
  "meta-llama/llama-3.3",
  "tinyllama/",
];

export function aittaReadsImages(model: string): boolean {
  const id = model.toLowerCase();
  return !AITTA_TEXT_ONLY.some((prefix) => id.startsWith(prefix));
}

/** How the active model takes part in the demo at `path`. */
export function modelUse(path: string, active: ActiveModel): ModelUse {
  const needs = PAGE_NEEDS[path] ?? {};
  const aitta = active.provider === "aitta";
  const serverOnlyPage = SERVER_MODEL_ONLY_PAGES.includes(path);
  const details: string[] = [];
  let problem: string | null = null;

  let runsHere = pageUsesModelSettings(path);
  if (serverOnlyPage) {
    if (active.own) runsHere = false;
    else if (path === "/transcriber") runsHere = aitta;
    // RAG needs embeddings from the same provider: Claude and Gemini have none here.
    else runsHere = ["azure", "openai", "aitta"].includes(active.provider);
  }

  if (!runsHere) {
    let summary = "This demo runs on the server's own model.";
    if (path === "/transcriber")
      summary = active.own
        ? "This demo transcribes on the server. Your key is not used here."
        : "This demo transcribes on the server. The picked model is not used here.";
    else if (active.own)
      summary =
        "This demo runs on the server's own model. Your key is not used here.";
    else if (!active.isDefault)
      summary = `This demo runs on the server's own model, not ${active.label}.`;
    return { runsHere, summary, details, problem };
  }

  if (path === "/transcriber") {
    return {
      runsHere,
      summary: `${AITTA_SPEECH_MODEL} on CSC Aitta transcribes here.`,
      details,
      problem,
    };
  }

  if (needs.speech) {
    if (aitta)
      details.push(
        `Recordings are transcribed by ${AITTA_SPEECH_MODEL} on CSC Aitta.`,
      );
    else if (!active.audio)
      details.push("Recordings are transcribed on the server first.");
  }
  if (needs.embeddings && aitta)
    details.push(`Embeddings come from ${AITTA_EMBEDDING_MODEL} on CSC Aitta.`);
  if (needs.embeddings && !active.isDefault)
    details.push(
      "A collection keeps the models it was built with: load the documents again after switching.",
    );
  if (needs.vision && !active.vision) {
    problem =
      needs.vision === "always"
        ? `${active.label} cannot read images, and this demo sends pages as images. Pick a model that reads images.`
        : `${active.label} cannot read images. Text works here; scans and image parsers need a model that reads images.`;
  }
  return {
    runsHere,
    summary: active.own
      ? `Your own model runs this demo: ${active.label}.`
      : `${active.label} runs this demo.`,
    details,
    problem,
  };
}
