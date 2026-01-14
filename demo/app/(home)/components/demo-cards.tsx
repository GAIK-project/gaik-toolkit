"use client";

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
  FileSearch,
  FileText,
  FolderKanban,
  type LucideIcon,
  Mic,
} from "lucide-react";
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

const features = [
  "Voice & Text Input",
  "Automatic Extraction",
  "Structured JSON",
  "PDF Generation",
];

export function DemoCards() {
  const featuredDemo = demos.find((demo) => demo.featured);
  const otherDemos = demos.filter((demo) => !demo.featured);

  return (
    <section id="demos" className="space-y-6">
      <h2 className="font-serif text-2xl font-semibold md:text-3xl">Demos</h2>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        {featuredDemo && (
          <div className="h-full">
            <Link href={featuredDemo.href} className="block h-full">
              <Card className="border-primary/20 bg-card hover:border-primary/40 group relative h-full overflow-hidden border transition-colors duration-200 hover:shadow-md">
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-4">
                    <div className="bg-primary/10 flex h-12 w-12 items-center justify-center rounded-xl">
                      <featuredDemo.icon className="text-primary h-6 w-6" />
                    </div>
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <CardTitle className="text-xl">
                          {featuredDemo.title}
                        </CardTitle>
                        <Badge className="bg-primary/15 text-primary hover:bg-primary/15 border-none">
                          Featured
                        </Badge>
                      </div>
                      <CardDescription>
                        {featuredDemo.description}
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="flex flex-wrap gap-2 pb-4">
                  {features.map((feature) => (
                    <span
                      key={feature}
                      className="bg-muted text-muted-foreground rounded-full px-3 py-1 text-xs"
                    >
                      {feature}
                    </span>
                  ))}
                </CardContent>

                <CardContent className="p-0">
                  <video
                    src="/video/incident-veo.mp4"
                    poster="/start.png"
                    autoPlay
                    muted
                    playsInline
                    preload="auto"
                    className="w-full"
                    onTimeUpdate={(e) => {
                      const video = e.currentTarget;
                      if (video.duration - video.currentTime < 1.5) {
                        video.pause();
                      }
                    }}
                  />
                </CardContent>
              </Card>
            </Link>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
          {otherDemos.map((demo) => (
            <Link key={demo.href} href={demo.href} className="block h-full">
              <Card className="bg-card hover:border-primary/40 group h-full border transition-colors duration-200 hover:shadow-md">
                <CardHeader>
                  <div className="bg-primary/5 mb-3 flex h-10 w-10 items-center justify-center rounded-lg">
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
