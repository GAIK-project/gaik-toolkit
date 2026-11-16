import { GitHubIcon } from "@/components/github-icon";
import { Button } from "@/components/ui/button";
import { AudioLines, Download, FileText, Table2, Tags } from "lucide-react";
import type { Metadata } from "next";

const REPO = "https://github.com/GAIK-project/gaik-toolkit-desktop";

export const metadata: Metadata = {
  title: "Desktop app",
  description:
    "GAIK Desktop runs the toolkit on files on your own computer, with your own model key.",
};

const tools = [
  {
    icon: Table2,
    name: "Extract data",
    text: "Describe the fields in your own words and get one row per file, with export to Excel, CSV or JSON.",
  },
  {
    icon: FileText,
    name: "Parse to text",
    text: "PDF and Word files to text. Files with a text layer are read without a model.",
  },
  {
    icon: Tags,
    name: "Classify",
    text: "Sort documents into your own classes, each with a confidence and a reason.",
  },
  {
    icon: AudioLines,
    name: "Transcribe",
    text: "Audio and video recordings to text, with an optional correction pass.",
  },
];

export default function DesktopAppPage() {
  return (
    <div className="space-y-10">
      <header className="space-y-5">
        <div className="space-y-2">
          <h1 className="font-serif text-3xl font-semibold tracking-tight md:text-4xl">
            Desktop app
          </h1>
          <p className="text-muted-foreground max-w-2xl">
            GAIK Desktop runs the toolkit on your own computer. Drop files or a
            whole folder: they are read where they are, and only their text or
            page images go to your own Azure OpenAI or OpenAI account. No
            sign-in to this demo is needed.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button asChild size="lg">
            <a href={`${REPO}/releases/latest`} target="_blank" rel="noopener noreferrer">
              <Download aria-hidden="true" />
              Download for Windows
            </a>
          </Button>
          <Button asChild size="lg" variant="outline">
            <a href={REPO} target="_blank" rel="noopener noreferrer">
              <GitHubIcon className="size-4" />
              Source code
            </a>
          </Button>
        </div>
        <p className="text-muted-foreground max-w-2xl text-sm">
          Experimental and tried on Windows 11 only. The installer is not
          code-signed, so Windows asks you to confirm it: choose More info, then
          Run anyway. The first start downloads about 350 MB.
        </p>
      </header>

      <video
        src="/downloads/desktop-app/gaik-desktop.mp4"
        poster="/downloads/desktop-app/gaik-desktop-poster.jpg"
        aria-label="GAIK Desktop extracting invoice fields from five PDF files and classifying documents"
        controls
        muted
        playsInline
        preload="metadata"
        className="aspect-video w-full rounded-lg border bg-black"
      />

      <section aria-labelledby="desktop-tools" className="space-y-4">
        <h2 id="desktop-tools" className="font-serif text-2xl font-semibold">
          What it does
        </h2>
        <ul className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
          {tools.map(({ icon: Icon, name, text }) => (
            <li key={name} className="flex gap-3">
              <Icon className="text-primary mt-0.5 size-5 shrink-0" aria-hidden="true" />
              <div>
                <h3 className="font-medium">{name}</h3>
                <p className="text-muted-foreground text-sm">{text}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
