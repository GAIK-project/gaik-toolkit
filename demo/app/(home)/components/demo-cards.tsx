import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FileSearch, FileText, FolderKanban, Mic } from "lucide-react";
import Link from "next/link";

const demos = [
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
  return (
    <section className="mx-auto mt-16 grid max-w-4xl gap-6 md:grid-cols-2">
      {demos.map((demo) => (
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
    </section>
  );
}
