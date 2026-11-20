// The demos the home page lists.
import {
  ACCESS,
  CAPTURE,
  type KnowledgeProcess,
  SYNTHESIS,
} from "@/lib/knowledge-processes";
import {
  AlertTriangle,
  AudioWaveform,
  Bot,
  Braces,
  Calculator,
  Database,
  Download,
  FileBarChart,
  FileOutput,
  FilePen,
  FileSearch,
  FileStack,
  FileText,
  FileUp,
  FolderKanban,
  Globe,
  HardHat,
  Headset,
  House,
  LibraryBig,
  type LucideIcon,
  MessageSquareQuote,
  Mic,
  NotebookPen,
  Scale,
  ScanEye,
  Search,
  Sparkles,
  Table2,
  Users,
  Video,
  Volume2,
} from "lucide-react";
import type { ComponentType } from "react";

export interface FeatureItem {
  label: string;
  icon: LucideIcon;
}

export interface Demo {
  title: string;
  description: string;
  href: string;
  /** A glyph, or a real mark such as the EU flag where one names the subject. */
  icon: LucideIcon | ComponentType<{ className?: string }>;
  /** Knowledge process the demo belongs to; use cases span several and have none. */
  process?: KnowledgeProcess;
  image?: string;
  imagePosition?: string;
  featureList?: FeatureItem[];
  comingSoon?: boolean;
}

// Use cases: the featured ones get an image card, the rest a compact card.
export const featuredUseCases: Demo[] = [
  {
    title: "Purchase order processing",
    description:
      "Extract purchase orders and BOMs, price them from a price list and draft the order",
    href: "/luvata-order",
    icon: FileBarChart,
    image: "/purchase-order-v1.png",
    imagePosition: "center top",
    featureList: [
      { label: "PO + BOMs", icon: FileUp },
      { label: "Fee Pricing", icon: Calculator },
      { label: "Your Own Fields", icon: Sparkles },
      { label: "PDF Export", icon: Download },
    ],
  },
  {
    title: "Construction report writing",
    description:
      "Turn on-site voice notes and the customer's documents into a source-grounded report",
    href: "/report-writer-v2?example=house_condition_assessment",
    icon: House,
    image: "/report-writer-v3.png",
    imagePosition: "center top",
    featureList: [
      { label: "Voice Notes", icon: Mic },
      { label: "Customer Documents", icon: FileUp },
      { label: "Source-grounded", icon: Sparkles },
      { label: "Word Export", icon: Download },
    ],
  },
];

// EU AI Act screening is no use case: it has its own place under the hero
// (solution-tools.tsx).
export const useCases: Demo[] = [
  {
    title: "Helpdesk chatbot",
    description:
      "Answers from a service catalogue and FAQ, with hand-off to a person",
    href: "/helpdesk-chatbot",
    icon: Headset,
  },
  {
    title: "Video transcription and captioning",
    description:
      "Upload audio or video, or open the ready-made example, to generate subtitles and transcripts",
    href: "/dental-transcription",
    icon: Mic,
  },
  {
    title: "Semantic video search",
    description:
      "Ask in plain language and jump to the right moment in indexed videos",
    href: "/video-search",
    icon: Video,
  },
  {
    title: "Incident reporting",
    description:
      "Record an incident by voice or text and get a structured report",
    href: "/incident-report",
    icon: AlertTriangle,
  },
  {
    title: "Construction diary",
    description:
      "Get one entry per day from site notes or recordings, with links to the source",
    href: "/diary",
    icon: HardHat,
  },
];

// Software modules, in the menu's order.
export const modules: Demo[] = [
  {
    title: "Audio → structured data",
    description:
      "Transcribe audio files and automatically extract structured data",
    href: "/audio-structured",
    icon: AudioWaveform,
    process: CAPTURE,
    featureList: [
      { label: "Upload Audio", icon: FileUp },
      { label: "Auto Transcribe", icon: Mic },
      { label: "Extract Data", icon: Sparkles },
      { label: "PDF Export", icon: Download },
    ],
  },
  {
    title: "Document → structured data",
    description:
      "Parse PDF, Word documents, and images to automatically extract structured data",
    href: "/document-structured",
    icon: FileOutput,
    process: CAPTURE,
    featureList: [
      { label: "Upload Docs", icon: FileUp },
      { label: "Auto Parse", icon: FileText },
      { label: "Extract Data", icon: Sparkles },
      { label: "PDF Export", icon: Download },
    ],
  },
  {
    title: "RAG builder",
    description:
      "Index PDF documents and ask questions with AI-powered citations",
    href: "/rag",
    icon: Bot,
    process: ACCESS,
    featureList: [
      { label: "Upload PDFs", icon: FileUp },
      { label: "AI Search", icon: Search },
      { label: "Cited Answers", icon: MessageSquareQuote },
      { label: "Source Tracking", icon: Database },
    ],
  },
  {
    title: "Report writer",
    description:
      "Generate structured reports from documents, audio, images and spreadsheets, with per-section review",
    href: "/report-writer",
    icon: FileText,
    process: SYNTHESIS,
    featureList: [
      { label: "Mixed inputs", icon: FileUp },
      { label: "Agentic review", icon: Sparkles },
      { label: "Section dependencies", icon: Database },
      { label: "Config import/export", icon: Download },
    ],
  },
  {
    title: "Report writer v2",
    description:
      "Edit source files and evidence between normalization, curation and synthesis",
    href: "/report-writer-v2",
    icon: FilePen,
    process: SYNTHESIS,
    featureList: [
      { label: "Staged pipeline", icon: Sparkles },
      { label: "Editable workspace", icon: FilePen },
      { label: "Section dependencies", icon: Database },
      { label: "Workspace .zip export", icon: Download },
    ],
  },
];

// Software components, in the menu's order.
export const components: Demo[] = [
  {
    title: "Schema generator",
    description:
      "Turn extraction requirements into reusable Pydantic models and field policies",
    href: "/schema-generator",
    icon: Braces,
    process: CAPTURE,
  },
  {
    title: "Extractor",
    description:
      "Automatically find and list important details from any document",
    href: "/extractor",
    icon: FileSearch,
    process: CAPTURE,
  },
  {
    title: "Vision extractor",
    description:
      "Extract structured data from PDFs and images in one LLM call, with no separate parsing step",
    href: "/vision-extractor",
    icon: ScanEye,
    process: CAPTURE,
  },
  {
    title: "Parser",
    description:
      "Read text and layout from PDF, Word files, and images accurately",
    href: "/parser",
    icon: FileText,
    process: CAPTURE,
  },
  {
    title: "Classifier",
    description: "Automatically sort your files into the right folders",
    href: "/classifier",
    icon: FolderKanban,
    process: CAPTURE,
  },
  {
    title: "Transcriber",
    description:
      "Specialized transcribers with correction features to convert voice recordings and videos into clear, written text",
    href: "/transcriber",
    icon: Mic,
    process: CAPTURE,
  },
  {
    title: "Source normalizer",
    description:
      "Convert documents, spreadsheets, recordings and images into Markdown that keeps each file's name",
    href: "/source-normalizer",
    icon: FileStack,
    process: CAPTURE,
  },
  {
    title: "Web scraper",
    description:
      "Crawl a website into clean Markdown and extract structured data, with the page each value came from",
    href: "/web-scraper",
    icon: Globe,
    process: CAPTURE,
  },
  {
    title: "Knowledge curator",
    description:
      "Collect verified facts per topic from normalized sources, each with its exact quote and location",
    href: "/knowledge-curator",
    icon: LibraryBig,
    process: CAPTURE,
  },
  {
    title: "PostgreSQL agent",
    description:
      "Ask a database questions in plain language — the agent writes and runs read-only SQL",
    href: "/postgres-agent",
    icon: Database,
    process: ACCESS,
  },
  {
    title: "Tabular agent",
    description:
      "Upload a CSV or Excel file and ask it questions — even messy report-style sheets",
    href: "/tabular-agent",
    icon: Table2,
    process: ACCESS,
  },
  {
    title: "Text-to-speech",
    description:
      "Generate downloadable spoken audio from text in Finnish or English",
    href: "/text-to-speech",
    icon: Volume2,
    process: SYNTHESIS,
  },
  {
    title: "LLM as judge",
    description:
      "Score extractor output, detect hallucinations, and run a multi-model judge panel",
    href: "/llm-judge",
    icon: Scale,
    process: SYNTHESIS,
  },
  {
    title: "Knowledge synthesizer",
    description:
      "Write a reviewed, source-grounded report from curated facts, with citations and visible review edits",
    href: "/knowledge-synthesis",
    icon: NotebookPen,
    process: SYNTHESIS,
  },
];

/** The demos of one knowledge process, in list order. */
export function inProcess(demos: Demo[], process: KnowledgeProcess): Demo[] {
  return demos.filter((demo) => demo.process === process);
}
