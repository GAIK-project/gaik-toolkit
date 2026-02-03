"use client";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { TransitionPanel } from "@/components/ui/transition-panel";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  AudioWaveform,
  Bot,
  Cpu,
  Database,
  Download,
  ExternalLink,
  FileBarChart,
  FileOutput,
  FileSearch,
  FileText,
  FileUp,
  FolderKanban,
  Globe,
  GraduationCap,
  HardHat,
  Headset,
  Lock,
  type LucideIcon,
  MessageSquareQuote,
  Mic,
  Search,
  Sparkles,
  Users,
  Video,
} from "lucide-react";
import { motion } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.15 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: "easeOut" as const },
  },
};

interface FeatureItem {
  label: string;
  icon: LucideIcon;
}

interface Demo {
  title: string;
  description: string;
  href: string;
  icon: LucideIcon;
  featured?: boolean;
  size?: "large" | "wide";
  image?: string;
  imagePosition?: string;
  featureList?: FeatureItem[];
}

// Use Cases (featured demos)
const useCaseDemos: Demo[] = [
  {
    title: "Incident Reporting",
    description:
      "Record an incident, transcribe audio, and extract structured report",
    href: "/incident-report",
    icon: AlertTriangle,
    featured: true,
    size: "large",
    image: "/incident-report-v1.png",
    imagePosition: "center 45%",
    featureList: [
      { label: "Speak or Type", icon: Mic },
      { label: "Instant Analysis", icon: Sparkles },
      { label: "Organized Data", icon: Database },
      { label: "PDF Export", icon: Download },
    ],
  },
  {
    title: "Construction Diary",
    description:
      "Record daily construction site activities via voice or text. Extract structured data automatically.",
    href: "/diary",
    icon: HardHat,
    featured: true,
    size: "large",
    image: "/construction-diary-v1.png",
    imagePosition: "center 52%",
    featureList: [
      { label: "Voice or Text", icon: Mic },
      { label: "Multilingual", icon: Globe },
      { label: "Personnel Tracking", icon: Users },
      { label: "PDF Export", icon: Download },
    ],
  },
];

// Software Modules (moved RAG here)
const moduleDemos: Demo[] = [
  {
    title: "RAG Builder",
    description:
      "Index PDF documents and ask questions with AI-powered citations",
    href: "/rag",
    icon: Bot,
    featured: true,
    size: "large",
    image: "/rag-builder-v1.png",
    imagePosition: "center 50%",
    featureList: [
      { label: "Upload PDFs", icon: FileUp },
      { label: "AI Search", icon: Search },
      { label: "Cited Answers", icon: MessageSquareQuote },
      { label: "Source Tracking", icon: Database },
    ],
  },
];

// Building Blocks (software components)
const buildingBlocks: Demo[] = [
  {
    title: "Data Extraction",
    description:
      "Automatically find and list important details from any document",
    href: "/extractor",
    icon: FileSearch,
  },
  {
    title: "Document Reader",
    description: "Read text and layout from PDF and Word files accurately",
    href: "/parser",
    icon: FileText,
  },
  {
    title: "Document Sorter",
    description: "Automatically sort your files into the right folders",
    href: "/classifier",
    icon: FolderKanban,
  },
  {
    title: "Speech to Text",
    description: "Convert voice recordings and videos into clear, written text",
    href: "/transcriber",
    icon: Mic,
  },
];

// Coming Soon items
const comingSoonUseCases = [
  { title: "Customer Assistant", icon: Headset },
  { title: "Learning Assistant", icon: GraduationCap },
  { title: "Semantic Video Search", icon: Video },
  { title: "Sales Proposal", icon: FileBarChart },
];

const comingSoonModules = [
  { title: "Audio → Structured Data", icon: AudioWaveform },
  { title: "Document → Structured Data", icon: FileOutput },
  { title: "Embedder", icon: Cpu },
  { title: "Vector Database", icon: Database },
];

// No-code Assets data with full details
const noCodeAssets = {
  prompts: [
    {
      title: "Incident Report Writing",
      description: "Extract structured incident data from transcripts",
      href: "https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/no-code-assets/prompts/Incident%20report%20writing",
      setup: "Paste in ChatGPT",
      output: "JSON (17 fields)",
    },
    {
      title: "Construction Diary Creation",
      description: "Extract construction site diary entries from recordings",
      href: "https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/no-code-assets/prompts/construction-diary-creation",
      setup: "Paste in ChatGPT",
      output: "JSON (20 fields)",
    },
    {
      title: "Purchase Order Processing",
      description: "Generate sales orders from PO + BOMs + price lists",
      href: "https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/no-code-assets/prompts/purchase-order-processing",
      setup: "Paste in ChatGPT",
      output: "Markdown + JSON",
    },
  ],
  skills: [
    {
      title: "Incident Report Writing",
      description: "Full audio → Word document pipeline",
      href: "https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/no-code-assets/agent-skills/incident-report-writing",
      setup: "Claude Desktop",
      output: "Word (.docx)",
    },
    {
      title: "Construction Diary Creation",
      description: "Audio transcription → structured diary",
      href: "https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/no-code-assets/agent-skills/construction-diary-creation",
      setup: "Claude Desktop",
      output: "Word (.docx)",
    },
    {
      title: "Purchase Order Processing",
      description: "PO + BOMs → priced sales order",
      href: "https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/no-code-assets/agent-skills/purchase-order-processing",
      setup: "Claude Desktop + MCP",
      output: "Word + breakdown",
    },
    {
      title: "Report Writing",
      description: "General report generation from audio",
      href: "https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/no-code-assets/agent-skills/report-writing-skill",
      setup: "Claude Desktop + MCP",
      output: "Word (.docx)",
    },
  ],
};

interface DemoCardsProps {
  isUnlocked: boolean;
}

function LockOverlay() {
  return (
    <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-black/50 opacity-0 transition-opacity group-hover:opacity-100">
      <div className="flex flex-col items-center gap-2 text-white">
        <Lock className="h-8 w-8" />
        <span className="text-sm font-medium">Sign in to access</span>
      </div>
    </div>
  );
}

function FeaturedCard({
  demo,
  isUnlocked,
}: {
  demo: Demo;
  isUnlocked: boolean;
}) {
  const isWide = demo.size === "wide";

  const cardContent = (
    <Card className="border-primary/20 bg-card hover:border-primary/40 group relative flex h-full flex-col overflow-hidden rounded-xl border transition-colors duration-200 hover:shadow-md">
      {!isUnlocked && <LockOverlay />}
      <CardHeader className="pb-3">
        <div className="flex items-center gap-4">
          <div className="bg-primary/10 flex h-12 w-12 shrink-0 items-center justify-center rounded-xl">
            <demo.icon className="text-primary h-6 w-6" />
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <CardTitle className="text-xl">{demo.title}</CardTitle>
              <Badge className="bg-primary/15 text-primary hover:bg-primary/15 border-none">
                Featured
              </Badge>
              {!isUnlocked && (
                <Lock className="text-muted-foreground h-4 w-4" />
              )}
            </div>
            <CardDescription>{demo.description}</CardDescription>
          </div>
        </div>
      </CardHeader>

      {isWide ? (
        // Wide card layout: stacked on mobile, horizontal on tablet+
        <CardContent className="flex flex-1 flex-col gap-4 pt-0 pb-6 sm:flex-row">
          {demo.image && (
            <div className="relative h-48 w-full shrink-0 overflow-hidden rounded-lg sm:h-56 sm:w-1/2">
              <Image
                src={demo.image}
                alt={`${demo.title} Demo`}
                fill
                className="object-cover object-center"
                style={{ objectPosition: "center 50%" }}
              />
            </div>
          )}
          {demo.featureList && (
            <div className="grid flex-1 grid-cols-2 gap-3">
              {demo.featureList.map((feature) => (
                <div
                  key={feature.label}
                  className="bg-muted/50 flex flex-col items-center justify-center gap-2 rounded-lg p-3"
                >
                  <div className="bg-background flex h-9 w-9 items-center justify-center rounded-full shadow-sm">
                    <feature.icon className="text-primary h-4 w-4" />
                  </div>
                  <span className="text-center text-sm font-medium">
                    {feature.label}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      ) : (
        // Regular large card layout: vertical
        <>
          {demo.image && (
            <CardContent className="-mt-2 overflow-hidden px-4 pt-0">
              <div className="relative h-56 overflow-hidden rounded-lg lg:h-64">
                <Image
                  src={demo.image}
                  alt={`${demo.title} Demo`}
                  fill
                  className="object-cover object-center"
                  style={{ objectPosition: demo.imagePosition || "center 60%" }}
                />
              </div>
            </CardContent>
          )}

          {demo.featureList && (
            <CardContent className="mt-auto flex-1 pt-2 pb-6">
              <div className="grid h-full grid-cols-2 gap-3">
                {demo.featureList.map((feature) => (
                  <div
                    key={feature.label}
                    className="bg-muted/50 flex flex-col items-center justify-center gap-2 rounded-lg p-4"
                  >
                    <div className="bg-background flex h-10 w-10 items-center justify-center rounded-full shadow-sm">
                      <feature.icon className="text-primary h-5 w-5" />
                    </div>
                    <span className="text-sm font-medium">{feature.label}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          )}
        </>
      )}
    </Card>
  );

  return (
    <Link href={isUnlocked ? demo.href : "/sign-in"} className="block h-full">
      {cardContent}
    </Link>
  );
}

function BuildingBlockCard({
  demo,
  isUnlocked,
}: {
  demo: Demo;
  isUnlocked: boolean;
}) {
  return (
    <Link href={isUnlocked ? demo.href : "/sign-in"} className="block h-full">
      <Card className="bg-card hover:border-primary/40 group relative h-full overflow-hidden rounded-xl border transition-colors duration-200 hover:shadow-md">
        {!isUnlocked && <LockOverlay />}
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="bg-primary/5 mb-3 flex h-10 w-10 items-center justify-center rounded-lg">
              <demo.icon className="text-primary h-5 w-5" />
            </div>
            {!isUnlocked && <Lock className="text-muted-foreground h-4 w-4" />}
          </div>
          <CardTitle className="text-lg">{demo.title}</CardTitle>
          <CardDescription>{demo.description}</CardDescription>
        </CardHeader>
      </Card>
    </Link>
  );
}

function ComingSoonItem({
  title,
  icon: Icon,
}: {
  title: string;
  icon: LucideIcon;
}) {
  return (
    <div className="text-muted-foreground/60 flex items-center gap-2 px-3 py-1.5 text-sm">
      <Icon className="h-4 w-4" />
      <span>{title}</span>
      <span className="bg-muted ml-auto rounded px-1.5 py-0.5 text-[10px]">
        Soon
      </span>
    </div>
  );
}

function ComingSoonSection({
  title,
  items,
}: {
  title: string;
  items: { title: string; icon: LucideIcon }[];
}) {
  return (
    <div className="border-muted-foreground/20 rounded-lg border border-dashed p-4">
      <h4 className="text-muted-foreground mb-2 text-sm font-medium">
        {title}
      </h4>
      <div className="grid grid-cols-2 gap-1">
        {items.map((item) => (
          <ComingSoonItem key={item.title} {...item} />
        ))}
      </div>
    </div>
  );
}

function NoCodeAssetItem({
  title,
  description,
  href,
  setup,
  output,
  type,
}: {
  title: string;
  description: string;
  href: string;
  setup: string;
  output: string;
  type: "prompt" | "skill";
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="block h-full"
    >
      <Card className="bg-card hover:border-primary/40 group relative h-full overflow-hidden rounded-xl border transition-colors duration-200 hover:shadow-md">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <Badge variant={type === "prompt" ? "secondary" : "default"}>
              {type === "prompt" ? "Prompt" : "Skill"}
            </Badge>
            <ExternalLink className="text-muted-foreground h-4 w-4" />
          </div>
          <CardTitle className="text-base">{title}</CardTitle>
          <CardDescription className="text-sm">{description}</CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="bg-muted rounded px-2 py-1">{setup}</span>
            <span className="bg-muted rounded px-2 py-1">{output}</span>
          </div>
        </CardContent>
      </Card>
    </a>
  );
}

function NoCodeAssetsSection() {
  const [activeTab, setActiveTab] = useState(0);
  const tabs = ["Prompts", "Agent Skills"];

  return (
    <motion.div variants={itemVariants} className="space-y-4">
      <h2 className="font-serif text-2xl font-semibold md:text-3xl">
        No-code Assets
      </h2>
      <p className="text-muted-foreground text-sm">
        Ready-to-use prompts and Claude Desktop skills. Click to view on GitHub.
      </p>

      {/* Tabs */}
      <div className="flex space-x-2">
        {tabs.map((tab, index) => (
          <button
            key={tab}
            onClick={() => setActiveTab(index)}
            className={cn(
              "rounded-md px-4 py-2 text-sm font-medium transition",
              activeTab === index
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/80",
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Content */}
      <TransitionPanel
        activeIndex={activeTab}
        transition={{ duration: 0.2, ease: "easeInOut" }}
        variants={{
          enter: { opacity: 0, y: -20, filter: "blur(4px)" },
          center: { opacity: 1, y: 0, filter: "blur(0px)" },
          exit: { opacity: 0, y: 20, filter: "blur(4px)" },
        }}
      >
        {/* Prompts Tab */}
        <div className="grid gap-4 pt-4 sm:grid-cols-2 lg:grid-cols-3">
          {noCodeAssets.prompts.map((item) => (
            <NoCodeAssetItem key={item.title} {...item} type="prompt" />
          ))}
        </div>

        {/* Skills Tab */}
        <div className="grid gap-4 pt-4 sm:grid-cols-2">
          {noCodeAssets.skills.map((item) => (
            <NoCodeAssetItem key={item.title} {...item} type="skill" />
          ))}
        </div>
      </TransitionPanel>
    </motion.div>
  );
}

export function DemoCards({ isUnlocked }: DemoCardsProps) {
  return (
    <motion.section
      id="demos"
      initial="hidden"
      animate="visible"
      variants={containerVariants}
      className="space-y-8"
    >
      {!isUnlocked && (
        <motion.div
          variants={itemVariants}
          className="bg-muted/50 border-primary/20 flex items-center gap-3 rounded-lg border p-4"
        >
          <Lock className="text-primary h-5 w-5 shrink-0" />
          <p className="text-muted-foreground text-sm">
            <Link href="/sign-in" className="text-primary hover:underline">
              Sign in
            </Link>{" "}
            to access the interactive demos. Don&apos;t have an account?{" "}
            <Link href="/sign-up" className="text-primary hover:underline">
              Sign up
            </Link>
            .
          </p>
        </motion.div>
      )}

      {/* Use Cases */}
      <motion.div variants={itemVariants} className="space-y-4">
        <h2 className="font-serif text-2xl font-semibold md:text-3xl">
          Use Cases
        </h2>
        <div className="grid gap-6 md:grid-cols-2">
          {useCaseDemos.map((demo) => (
            <motion.div
              key={demo.href}
              variants={itemVariants}
              className={demo.size === "wide" ? "md:col-span-2" : ""}
            >
              <FeaturedCard demo={demo} isUnlocked={isUnlocked} />
            </motion.div>
          ))}
        </div>
        <ComingSoonSection
          title="More Use Cases Coming"
          items={comingSoonUseCases}
        />
      </motion.div>

      {/* Software Modules */}
      <motion.div variants={itemVariants} className="space-y-4">
        <h2 className="font-serif text-2xl font-semibold md:text-3xl">
          Software Modules
        </h2>
        <div className="grid gap-6 md:grid-cols-2">
          {moduleDemos.map((demo) => (
            <motion.div
              key={demo.href}
              variants={itemVariants}
              className={
                moduleDemos.length === 1
                  ? "md:col-span-2"
                  : demo.size === "wide"
                    ? "md:col-span-2"
                    : ""
              }
            >
              <FeaturedCard demo={demo} isUnlocked={isUnlocked} />
            </motion.div>
          ))}
        </div>
        <ComingSoonSection
          title="More Modules Coming"
          items={comingSoonModules}
        />
      </motion.div>

      {/* Software Components */}
      <motion.div variants={itemVariants} className="space-y-4">
        <h2 className="font-serif text-2xl font-semibold md:text-3xl">
          Software Components
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {buildingBlocks.map((demo) => (
            <motion.div key={demo.href} variants={itemVariants}>
              <BuildingBlockCard demo={demo} isUnlocked={isUnlocked} />
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* No-code Assets */}
      <NoCodeAssetsSection />
    </motion.section>
  );
}
