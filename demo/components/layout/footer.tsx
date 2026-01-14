import { BookOpen } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import {
  Glimpse,
  GlimpseTrigger,
  GlimpseContent,
  GlimpseTitle,
  GlimpseDescription,
  GlimpseImage,
} from "@/components/kibo-ui/glimpse";
import type { LinkPreview } from "@/lib/link-previews";

const GITHUB_URL = "https://github.com/GAIK-project/gaik-toolkit";
const DOCS_URL = "https://gaik-toolkit.2.rahtiapp.fi/";

export interface FooterProps {
  githubPreview?: LinkPreview | null;
}

export function Footer({ githubPreview }: FooterProps) {
  const currentYear = new Date().getFullYear();

  const githubLink = (
    <a
      href={GITHUB_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="text-muted-foreground hover:text-foreground flex items-center gap-1.5 transition-colors"
    >
      <Image
        src="/logos/github-mark-white.svg"
        alt=""
        width={14}
        height={14}
        className="dark:invert-0 invert"
      />
      GitHub
    </a>
  );

  return (
    <footer className="border-t">
      <div className="container mx-auto px-4 py-4">
        <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <div className="flex items-center gap-2">
            <Link href="/" className="shrink-0">
              <Image
                src="/logos/gaik-logo-letter-only.png"
                alt="GAIK"
                width={24}
                height={24}
                className="h-6 w-6"
              />
            </Link>
            <span className="text-muted-foreground text-sm">
              &copy; {currentYear} GAIK Project
            </span>
          </div>

          <nav className="text-muted-foreground flex items-center gap-4 text-sm">
            {githubPreview ? (
              <Glimpse>
                <GlimpseTrigger asChild>{githubLink}</GlimpseTrigger>
                <GlimpseContent className="w-80">
                  {githubPreview.image && (
                    <GlimpseImage
                      src={githubPreview.image}
                      alt={githubPreview.title || "GitHub"}
                    />
                  )}
                  <GlimpseTitle>
                    {githubPreview.title || "GAIK Toolkit"}
                  </GlimpseTitle>
                  <GlimpseDescription>
                    {githubPreview.description ||
                      "AI-powered document processing toolkit"}
                  </GlimpseDescription>
                </GlimpseContent>
              </Glimpse>
            ) : (
              githubLink
            )}
            <span className="text-border">|</span>
            <a
              href={DOCS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-foreground flex items-center gap-1.5 transition-colors"
            >
              <BookOpen className="h-3.5 w-3.5" />
              Docs
            </a>
          </nav>
        </div>
      </div>
    </footer>
  );
}
