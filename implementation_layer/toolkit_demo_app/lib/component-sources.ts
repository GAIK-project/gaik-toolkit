// Where the code behind each demo lives, how to install the gaik parts it uses, and
// where the docs describe it. The demo header reads it by route.
import { GITHUB_REPO_URL } from "@/lib/link-previews";

export const DOCS_URL = "https://gaik-project.github.io/gaik-toolkit";

const SOURCE_ROOT = `${GITHUB_REPO_URL}/tree/main/implementation_layer/src/gaik`;
const DEMO_ROOT = `${GITHUB_REPO_URL}/blob/main/implementation_layer/toolkit_demo_app`;
const COMPONENTS_DOCS = `${DOCS_URL}/toolkit/software-components/`;
const MODULES_DOCS = `${DOCS_URL}/toolkit/software-modules/`;

export interface ComponentSource {
  /** The pip extras that install what the demo uses; empty when it uses no gaik code. */
  extras: string[];
  /** A component or module: its package folder. A use case: the demo's own backend code. */
  sourceUrl: string;
  /** The docs page or section that describes it, if there is one. */
  docsUrl: string | null;
}

function component(
  extra: string,
  folder: string,
  docsAnchor: string,
): ComponentSource {
  return {
    extras: [extra],
    sourceUrl: `${SOURCE_ROOT}/software_components/${folder}`,
    docsUrl: `${COMPONENTS_DOCS}#${docsAnchor}`,
  };
}

function softwareModule(
  extra: string,
  folder: string,
  docsAnchor: string,
): ComponentSource {
  return {
    extras: [extra],
    sourceUrl: `${SOURCE_ROOT}/software_modules/${folder}`,
    docsUrl: `${MODULES_DOCS}#${docsAnchor}`,
  };
}

/** A use case combines several components; its source is the demo code that does it. */
function combination(
  extras: string[],
  demoFile: string,
  docsPage: string | null,
): ComponentSource {
  return {
    extras,
    sourceUrl: `${DEMO_ROOT}/${demoFile}`,
    docsUrl: docsPage ? `${DOCS_URL}/use-cases/${docsPage}/` : null,
  };
}

const SOURCES: Record<string, ComponentSource> = {
  "/schema-generator": component("extract", "schema_generator", "extractor"),
  "/extractor": component("extract", "extractor", "extractor"),
  "/vision-extractor": component(
    "vision-extract",
    "vision_extractor",
    "vision-extractor",
  ),
  "/parser": component("parser", "parsers", "document-parser"),
  "/classifier": component(
    "classifier",
    "doc_classifier",
    "document-classifier",
  ),
  "/transcriber": component("transcriber", "transcriber", "transcriber"),
  "/source-normalizer": component(
    "source-normalizer",
    "source_normalizer",
    "source-normalizer",
  ),
  "/web-scraper": component("web-scraper", "web_scraper", "web-scraper"),
  "/knowledge-curator": component(
    "knowledge-curator",
    "knowledge_curator",
    "knowledge-curator",
  ),
  "/postgres-agent": component(
    "postgres-agent",
    "postgres_agent",
    "postgres-agent",
  ),
  "/tabular-agent": component(
    "tabular-agent",
    "tabular_agent",
    "tabular-agent",
  ),
  "/text-to-speech": component(
    "text-to-speech",
    "text_to_speech",
    "text-to-speech",
  ),
  "/llm-judge": component("llm-judge", "validators", "validator-llm-as-judge"),
  "/knowledge-synthesis": component(
    "report-synthesizer",
    "report_synthesizer",
    "report-synthesizer",
  ),
  "/rag": component("rag-workflow", "RAG", "rag-components"),
  "/audio-structured": softwareModule(
    "audio-to-structured-data",
    "audio_to_structured_data",
    "audio-to-structured-data",
  ),
  "/document-structured": softwareModule(
    "documents-to-structured-data",
    "documents_to_structured_data",
    "document-to-structured-data",
  ),
  "/report-writer": softwareModule(
    "multi-source-report-generator",
    "multi_source_report_generator",
    "multi-source-report-generator-legacy",
  ),
  "/report-writer-v2": softwareModule(
    "report-writer",
    "report_writer",
    "report-writer",
  ),
  "/luvata-order": combination(
    ["parser", "extract"],
    "api/routers/luvata_order.py",
    "purchase-order-processing",
  ),
  "/incident-report": combination(
    ["transcriber", "parser", "vision-extract"],
    "api/routers/pipeline.py",
    "incident-reporting",
  ),
  "/diary": combination(
    ["transcriber", "parser", "vision-extract"],
    "api/routers/pipeline.py",
    "construction-site-diary-creation",
  ),
  "/dental-transcription": combination(
    ["transcriber"],
    "api/routers/dental_transcription.py",
    "transcription-captioning-translation",
  ),
  "/video-search": combination(
    ["pg-vector-store", "embedder", "transcriber"],
    "api/routers/video_search.py",
    "semantic-video-search",
  ),
  // Runs in the Next.js app itself, with no gaik code.
  "/helpdesk-chatbot": combination([], "lib/helpdesk-chatbot/agent.ts", null),
};

export function componentSourceFor(pathname: string): ComponentSource | null {
  return SOURCES[pathname.replace(/\/+$/, "") || "/"] ?? null;
}

/** Quoted, so the brackets also work in zsh. */
export function installCommand(extras: string[]): string {
  return `pip install "gaik[${extras.join(",")}]"`;
}

export const componentSourceRoutes = Object.keys(SOURCES);
