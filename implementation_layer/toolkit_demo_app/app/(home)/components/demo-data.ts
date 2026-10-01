// The demos the home page lists. The hero reads it too, for its process overview.
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
  Cpu,
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
  GraduationCap,
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

export interface FeatureItem {
  label: string;
  icon: LucideIcon;
}

export interface Demo {
  title: string;
  description: string;
  href: string;
  icon: LucideIcon;
  /** Knowledge process the demo belongs to; use cases span several and have none. */
  process?: KnowledgeProcess;
  image?: string;
  imagePosition?: string;
  featureList?: FeatureItem[];
  comingSoon?: boolean;
}

export interface ComingSoon {
  title: string;
  icon: LucideIcon;
}

// Use cases: the featured ones get an image card, the rest a compact card.
export const featuredUseCases: Demo[] = [
  {
    title: "Purchase Order Processing",
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
    title: "Construction Report Writing",
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

export const useCases: Demo[] = [
  {
    title: "Video Transcription & Captioning",
    description:
      "Upload audio or video, or open the ready-made example, to generate subtitles and transcripts",
    href: "/dental-transcription",
    icon: Mic,
  },
  {
    title: "Semantic Video Search",
    description:
      "Ask in plain language and jump to the right moment in indexed videos",
    href: "/video-search",
    icon: Video,
  },
  {
    title: "Incident Reporting",
    description:
      "Record an incident by voice or text and get a structured report",
    href: "/incident-report",
    icon: AlertTriangle,
  },
  {
    title: "Construction Diary",
    description:
      "Log daily site activities by voice or text and extract structured data",
    href: "/diary",
    icon: HardHat,
  },
];

export const comingSoonUseCases: ComingSoon[] = [
  { title: "Customer onboarding and sales assistant", icon: Headset },
  { title: "Sales Proposal Generation", icon: FileBarChart },
  { title: "Learning plans & recommendations", icon: GraduationCap },
];

// Software modules, in the menu's order.
export const modules: Demo[] = [
  {
    title: "Audio → Structured Data",
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
    title: "Document → Structured Data",
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
    title: "RAG Builder",
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
    title: "Report Writer",
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
    title: "Report Writer v2",
    description:
      "Write a report in stages — normalize, curate, synthesize, review — and edit every file in between",
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
    title: "Schema Generator",
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
    title: "Vision Extractor",
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
    title: "Source Normalizer",
    description:
      "Convert documents, spreadsheets, recordings and images into Markdown that keeps each file's name",
    href: "/source-normalizer",
    icon: FileStack,
    process: CAPTURE,
  },
  {
    title: "Knowledge Curator",
    description:
      "Collect verified facts per topic from normalized sources, each with its exact quote and location",
    href: "/knowledge-curator",
    icon: LibraryBig,
    process: CAPTURE,
  },
  {
    title: "PostgreSQL Agent",
    description:
      "Ask a database questions in plain language — the agent writes and runs read-only SQL",
    href: "/postgres-agent",
    icon: Database,
    process: ACCESS,
  },
  {
    title: "Tabular Agent",
    description:
      "Upload a CSV or Excel file and ask it questions — even messy report-style sheets",
    href: "/tabular-agent",
    icon: Table2,
    process: ACCESS,
  },
  {
    title: "Text-to-Speech",
    description:
      "Generate downloadable spoken audio from text in Finnish or English",
    href: "/text-to-speech",
    icon: Volume2,
    process: SYNTHESIS,
  },
  {
    title: "LLM-as-Judge",
    description:
      "Score extractor output, detect hallucinations, and run a multi-model judge panel",
    href: "/llm-judge",
    icon: Scale,
    process: SYNTHESIS,
  },
  {
    title: "Knowledge Synthesizer",
    description:
      "Write a reviewed, source-grounded report from curated facts, with citations and visible review edits",
    href: "/knowledge-synthesis",
    icon: NotebookPen,
    process: SYNTHESIS,
  },
];

export const comingSoonComponents: ComingSoon[] = [
  { title: "Retriever", icon: Search },
  { title: "Embedder", icon: Cpu },
  { title: "Vector Database", icon: Database },
];

/** The demos of one knowledge process, in list order. */
export function inProcess(demos: Demo[], process: KnowledgeProcess): Demo[] {
  return demos.filter((demo) => demo.process === process);
}
