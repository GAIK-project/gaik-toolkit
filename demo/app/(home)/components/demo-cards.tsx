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
  Database,
  Download,
  FileSearch,
  FileText,
  FolderKanban,
  type LucideIcon,
  Mic,
  Sparkles,
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

const featureList = [
  { label: "Speak or Type", icon: Mic },
  { label: "Instant Analysis", icon: Sparkles },
  { label: "Organized Data", icon: Database },
  { label: "PDF Export", icon: Download },
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

                <CardContent className="overflow-hidden px-4">
                  <video
                    src="/video/incident-veo.mp4"
                    poster="/start.png"
                    autoPlay
                    loop
                    muted
                    playsInline
                    preload="auto"
                    className="w-full rounded-lg"
                  />
                </CardContent>

                <CardContent className="pt-2 pb-6">
                  <div className="grid grid-cols-2 gap-3">
                    {featureList.map((feature) => (
                      <div
                        key={feature.label}
                        className="bg-muted/50 flex items-center gap-3 rounded-lg p-3"
                      >
                        <div className="bg-background flex h-8 w-8 items-center justify-center rounded-full shadow-sm">
                          <feature.icon className="text-primary h-4 w-4" />
                        </div>
                        <span className="text-sm font-medium">
                          {feature.label}
                        </span>
                      </div>
                    ))}
                  </div>
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
