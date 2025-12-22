import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileSearch, FileText, FolderKanban, Mic, Workflow } from "lucide-react";
import Link from "next/link";

const demos = [
  {
    title: "Pipeline Demo",
    description: "End-to-end workflows: Audio/Document to Structured Data with PDF export",
    href: "/pipeline",
    icon: Workflow,
    featured: true,
  },
  {
    title: "Extractor",
    description: "Extract structured data from documents using natural language",
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
  const featuredDemo = demos.find((d) => d.featured);
  const otherDemos = demos.filter((d) => !d.featured);

  return (
    <section className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <h2 className="text-2xl font-semibold font-serif md:text-3xl">Demos</h2>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        {/* Featured Pipeline Demo */}
        {featuredDemo && (
          <Link href={featuredDemo.href} className="group">
            <Card className="relative h-full overflow-hidden border border-primary/20 bg-card transition-all duration-300 hover:-translate-y-1 hover:border-primary/40 hover:shadow-lg">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/15">
                    <featuredDemo.icon className="h-6 w-6 text-primary" />
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
                    <CardDescription>{featuredDemo.description}</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex min-h-[180px] items-center justify-center text-sm text-muted-foreground">
                End-to-end workflow in one run.
              </CardContent>
            </Card>
          </Link>
        )}

        {/* Other demos grid */}
        <div className="grid gap-4 sm:grid-cols-2">
          {otherDemos.map((demo) => (
            <Link key={demo.href} href={demo.href} className="group">
              <Card className="h-full border bg-card transition-all duration-300 hover:-translate-y-1 hover:border-primary/40 hover:shadow-md">
                <CardHeader>
                  <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                    <demo.icon className="h-5 w-5 text-primary" />
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
