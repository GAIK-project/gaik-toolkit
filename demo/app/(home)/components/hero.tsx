import { Button } from "@/components/ui/button";

export function Hero() {
  return (
    <section className="mx-auto flex max-w-3xl flex-col items-center gap-6 text-center">
      <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
        GAIK Toolkit
      </h1>
      <p className="text-lg text-muted-foreground">
        Generative AI-Enhanced Knowledge Management components for document
        processing, extraction, classification, and transcription.
      </p>
      <div className="mt-4 flex gap-4">
        <Button size="lg" asChild>
          <a
            href="https://pypi.org/project/gaik/"
            target="_blank"
            rel="noopener noreferrer"
          >
            PyPI Package
          </a>
        </Button>
        <Button size="lg" variant="outline" asChild>
          <a
            href="https://github.com/GAIK-project/gaik-toolkit"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
        </Button>
      </div>
    </section>
  );
}
