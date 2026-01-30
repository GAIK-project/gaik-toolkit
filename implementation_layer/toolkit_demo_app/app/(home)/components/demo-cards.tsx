import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  AlertTriangle,
  Bot,
  Database,
  Download,
  FileSearch,
  FileText,
  FileUp,
  FolderKanban,
  Lock,
  type LucideIcon,
  MessageSquareQuote,
  Mic,
  Search,
  Sparkles,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";

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
  image?: string;
  featureList?: FeatureItem[];
}

const demos: Demo[] = [
  {
    title: "Incident Reporting",
    description:
      "Record an incident, transcribe audio, and extract structured report",
    href: "/incident-report",
    icon: AlertTriangle,
    featured: true,
    image: "/incident-report-v1.png",
    featureList: [
      { label: "Speak or Type", icon: Mic },
      { label: "Instant Analysis", icon: Sparkles },
      { label: "Organized Data", icon: Database },
      { label: "PDF Export", icon: Download },
    ],
  },
  {
    title: "RAG Builder",
    description:
      "Index PDF documents and ask questions with AI-powered citations",
    href: "/rag",
    icon: Bot,
    featured: true,
    image: "/rag-builder-v1.png",
    featureList: [
      { label: "Upload PDFs", icon: FileUp },
      { label: "AI Search", icon: Search },
      { label: "Cited Answers", icon: MessageSquareQuote },
      { label: "Source Tracking", icon: Database },
    ],
  },
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

      {demo.image && (
        <CardContent className="-mt-2 overflow-hidden px-4 pt-0">
          <div className="relative h-56 overflow-hidden rounded-lg lg:h-64">
            <Image
              src={demo.image}
              alt={`${demo.title} Demo`}
              fill
              className="object-cover object-center"
              style={{ objectPosition: "center 45%" }}
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

export function DemoCards({ isUnlocked }: DemoCardsProps) {
  const featuredDemos = demos.filter((demo) => demo.featured);
  const buildingBlocks = demos.filter((demo) => !demo.featured);

  return (
    <section id="demos" className="animate-in fade-in duration-500 delay-150 space-y-8">
      {!isUnlocked && (
        <div className="bg-muted/50 border-primary/20 flex items-center gap-3 rounded-lg border p-4">
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
        </div>
      )}

      {/* Use Cases - Featured */}
      <div className="space-y-4">
        <h2 className="font-serif text-2xl font-semibold md:text-3xl">
          Use Cases
        </h2>
        <div className="grid gap-6 md:grid-cols-2">
          {featuredDemos.map((demo) => (
            <FeaturedCard key={demo.href} demo={demo} isUnlocked={isUnlocked} />
          ))}
        </div>
      </div>

      {/* Building Blocks */}
      <div className="space-y-4">
        <h2 className="font-serif text-2xl font-semibold md:text-3xl">
          Building Blocks
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {buildingBlocks.map((demo) => (
            <BuildingBlockCard
              key={demo.href}
              demo={demo}
              isUnlocked={isUnlocked}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
