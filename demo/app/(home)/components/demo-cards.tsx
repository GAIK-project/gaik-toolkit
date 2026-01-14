import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  AlertTriangle,
  FileSearch,
  FileText,
  FolderKanban,
  type LucideIcon,
  Mic,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";

interface Demo {
  title: string;
  description: string;
  href: string;
  icon: LucideIcon;
  featured?: boolean;
}

const demos: Demo[] = [
  {
    title: "Incident Reporting",
    description:
      "Record an incident, transcribe audio, and extract structured report",
    href: "/incident-report",
    icon: AlertTriangle,
    featured: true,
  },
  {
    title: "Extractor",
    description:
      "Extract structured data from documents using natural language",
    href: "/extractor",
    icon: FileSearch,
  },
  {
    title: "Parser",
    description: "Parse PDFs and Word documents with vision models or PyMuPDF",
    href: "/parser",
    icon: FileText,
  },
  {
    title: "Classifier",
    description: "Classify documents into predefined categories using LLM",
    href: "/classifier",
    icon: FolderKanban,
  },
  {
    title: "Transcriber",
    description: "Transcribe audio and video with Whisper and GPT enhancement",
    href: "/transcriber",
    icon: Mic,
  },
];

export function DemoCards() {
  const featuredDemo = demos.find((demo) => demo.featured);
  const otherDemos = demos.filter((demo) => !demo.featured);

  return (
    <section id="demos" className="space-y-6">
      <h2 className="font-serif text-2xl font-semibold md:text-3xl">Demos</h2>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        {featuredDemo && (
          <Link href={featuredDemo.href}>
            <Card className="border-primary/20 bg-card hover:border-primary/40 relative h-full overflow-hidden border transition-all duration-300 hover:-translate-y-1 hover:shadow-lg">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-4">
                  <div className="bg-primary/15 flex h-12 w-12 items-center justify-center rounded-xl">
                    <featuredDemo.icon className="text-primary h-6 w-6" />
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-xl">
                        {featuredDemo.title}
                      </CardTitle>
                      <Badge className="bg-primary/15 text-primary">
                        Featured
                      </Badge>
                    </div>
                    <CardDescription>
                      {featuredDemo.description}
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="relative h-[160px] overflow-hidden p-0">
                <Image
                  src="/incident-report.png"
                  alt="Incident Report Demo"
                  fill
                  className="object-cover object-center"
                />
              </CardContent>
            </Card>
          </Link>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          {otherDemos.map((demo) => (
            <Link key={demo.href} href={demo.href}>
              <Card className="bg-card hover:border-primary/40 h-full border transition-all duration-300 hover:-translate-y-1 hover:shadow-md">
                <CardHeader>
                  <div className="bg-primary/10 mb-3 flex h-10 w-10 items-center justify-center rounded-lg">
                    <demo.icon className="text-primary h-5 w-5" />
                  </div>
                  <CardTitle className="text-lg">{demo.title}</CardTitle>
                  <CardDescription>{demo.description}</CardDescription>
                </CardHeader>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
