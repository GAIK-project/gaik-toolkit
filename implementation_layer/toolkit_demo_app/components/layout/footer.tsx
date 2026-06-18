"use client";

import { BookOpen, Compass, Shield, UserPlus } from "lucide-react";
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
import { useOnboarding } from "@/components/onboarding/onboarding-provider";
import { GITHUB_REPO_URL, type LinkPreview } from "@/lib/link-previews";
import { useEffect, useState } from "react";

const DOCS_URL = "https://gaik-toolkit.2.rahtiapp.fi/" as const;

export interface FooterProps {
  githubPreview?: LinkPreview | null;
}

export function Footer({ githubPreview }: FooterProps) {
  const currentYear = new Date().getFullYear();
  const { startTour } = useOnboarding();

  // Suppress hydration mismatch: GlimpseTrigger (Radix HoverCard asChild) renders
  // differently on the server vs. client. Only activate the hover card after mount.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

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
          <div className="flex items-center gap-4">
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
                &copy; {currentYear}{" "}
                <a
                  href="https://gaik.ai/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-foreground transition-colors"
                >
                  GAIK Project
                </a>
              </span>
            </div>
            <Image
              src="/co-funded_EN/horizontal/RGB/PNG/EN_Co-fundedbytheEU_RGB_POS.png"
              alt="Co-funded by the European Union"
              width={180}
              height={40}
              className="h-8 w-auto"
            />
          </div>

          <nav className="text-muted-foreground flex items-center gap-4 text-sm">
            {mounted && githubPreview ? (
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
              href="/privacy"
              className="hover:text-foreground flex items-center gap-1.5 transition-colors"
            >
              <Shield className="h-3.5 w-3.5" />
              Privacy
            </Link>
            <span className="text-border">|</span>
            <Link
              href="/sign-up"
              className="hover:text-foreground flex items-center gap-1.5 transition-colors"
            >
              <UserPlus className="h-3.5 w-3.5" />
              Request Access
            </Link>
            <span className="text-border">|</span>
            <button
              type="button"
              onClick={startTour}
              className="hover:text-foreground flex items-center gap-1.5 transition-colors"
            >
              <Compass className="h-3.5 w-3.5" />
              Take a tour
            </button>
          </nav>
        </div>
      </div>
    </footer>
  );
}
