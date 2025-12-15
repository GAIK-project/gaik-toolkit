import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
    <section className="mx-auto mt-16 max-w-4xl space-y-6">
      {/* Featured Pipeline Demo */}
      {featuredDemo && (
        <Link href={featuredDemo.href}>
          <Card className="transition-all hover:border-primary hover:shadow-lg border-2 border-primary/20 bg-linear-to-br from-primary/5 to-transparent">
            <CardHeader>
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                  <featuredDemo.icon className="h-6 w-6 text-primary" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-xl">{featuredDemo.title}</CardTitle>
                    <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full font-medium">
                      Featured
                    </span>
                  </div>
                  <CardDescription className="mt-1">
                    {featuredDemo.description}
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Try the complete end-to-end workflow demo
              </p>
            </CardContent>
          </Card>
        </Link>
      )}

      {/* Other demos grid */}
      <div className="grid gap-6 md:grid-cols-2">
        {otherDemos.map((demo) => (
          <Link key={demo.href} href={demo.href}>
            <Card className="h-full transition-colors hover:border-primary">
              <CardHeader>
                <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                  <demo.icon className="h-5 w-5 text-primary" />
                </div>
                <CardTitle>{demo.title}</CardTitle>
                <CardDescription>{demo.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Click to try the interactive demo
                </p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </section>
  );
}
