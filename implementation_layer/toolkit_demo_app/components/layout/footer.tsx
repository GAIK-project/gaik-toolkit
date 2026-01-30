import { BookOpen, UserPlus } from "lucide-react";
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
import { GitHubIcon } from "@/components/github-icon";
import { GITHUB_REPO_URL, type LinkPreview } from "@/lib/link-previews";

const DOCS_URL = "https://gaik-toolkit.2.rahtiapp.fi/";

export interface FooterProps {
  githubPreview?: LinkPreview | null;
}

export function Footer({ githubPreview }: FooterProps) {
  const currentYear = new Date().getFullYear();

  const githubLink = (
    <a
      href={GITHUB_REPO_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="text-muted-foreground hover:text-foreground flex items-center gap-1.5 transition-colors"
    >
      <GitHubIcon className="h-3.5 w-3.5" />
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
            <span className="text-border">|</span>
            <Link
              href="/sign-up"
              className="hover:text-foreground flex items-center gap-1.5 transition-colors"
            >
              <UserPlus className="h-3.5 w-3.5" />
              Request Access
            </Link>
          </nav>
        </div>
      </div>
    </footer>
  );
}
