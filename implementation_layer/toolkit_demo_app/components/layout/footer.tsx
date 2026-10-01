"use client";

import {
  BookOpen,
  Compass,
  Globe,
  Package,
  Shield,
  UserPlus,
} from "lucide-react";
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
import { useHasMounted } from "@/hooks/use-has-mounted";

const DOCS_URL = "https://gaik-project.github.io/gaik-toolkit/" as const;
const PYPI_URL = "https://pypi.org/project/gaik/" as const;

// Sections of the home page.
const DEMO_LINKS = [
  { href: "/#use-cases", label: "Use Cases" },
  { href: "/#modules", label: "Software Modules" },
  { href: "/#components", label: "Software Components" },
  { href: "/#no-code", label: "No-code Assets" },
] as const;

export interface FooterProps {
  githubPreview?: LinkPreview | null;
}

export function Footer({ githubPreview }: FooterProps) {
  const currentYear = new Date().getFullYear();
  const { startTour } = useOnboarding();

  // Suppress hydration mismatch: GlimpseTrigger (Radix HoverCard asChild) renders
  // differently on the server vs. client. Only activate the hover card after mount.
  const mounted = useHasMounted();

  const githubLink = (
    <a
      href={GITHUB_REPO_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="text-muted-foreground hover:text-foreground flex w-fit items-center gap-1.5 transition-colors"
    >
      <GitHubIcon className="h-3.5 w-3.5" />
      GitHub
    </a>
  );

  const linkClassName =
    "text-muted-foreground hover:text-foreground flex w-fit items-center gap-1.5 transition-colors";

  return (
    <footer className="bg-card/50 border-t">
      <div className="container mx-auto px-4 py-10">
        <div className="grid gap-10 md:grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,1fr))]">
          <div className="space-y-4">
            <Link href="/" className="flex w-fit items-center gap-2">
              <Image
                src="/logos/gaik-logo-letter-only.png"
                alt=""
                width={28}
                height={28}
                className="h-7 w-7"
              />
              <span className="font-semibold">GAIK Toolkit</span>
            </Link>
            <p className="text-muted-foreground max-w-xs text-sm">
              Generative AI building blocks for knowledge capture, access and
              synthesis.
            </p>
            <Image
              src="/co-funded_EN/horizontal/RGB/PNG/EN_Co-fundedbytheEU_RGB_POS.png"
              alt="Co-funded by the European Union"
              width={180}
              height={40}
              className="h-9 w-auto"
            />
          </div>

          <FooterColumn title="Demos">
            {DEMO_LINKS.map(({ href, label }) => (
              <Link key={href} href={href} className={linkClassName}>
                {label}
              </Link>
            ))}
          </FooterColumn>

          <FooterColumn title="Resources">
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
            <a
              href={DOCS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className={linkClassName}
            >
              <BookOpen className="h-3.5 w-3.5" />
              Docs
            </a>
            <a
              href={PYPI_URL}
              target="_blank"
              rel="noopener noreferrer"
              className={linkClassName}
            >
              <Package className="h-3.5 w-3.5" />
              PyPI
            </a>
          </FooterColumn>

          <FooterColumn title="Project">
            <a
              href="https://gaik.ai/"
              target="_blank"
              rel="noopener noreferrer"
              className={linkClassName}
            >
              <Globe className="h-3.5 w-3.5" />
              gaik.ai
            </a>
            <Link href="/sign-up" className={linkClassName}>
              <UserPlus className="h-3.5 w-3.5" />
              Request Access
            </Link>
            <button type="button" onClick={startTour} className={linkClassName}>
              <Compass className="h-3.5 w-3.5" />
              Take a tour
            </button>
            <Link href="/privacy" className={linkClassName}>
              <Shield className="h-3.5 w-3.5" />
              Privacy
            </Link>
          </FooterColumn>
        </div>

        <p className="text-muted-foreground mt-10 max-w-4xl border-t pt-6 text-xs leading-5">
          <strong className="text-foreground">Disclaimer:</strong>
          <span>{DISCLAIMER}</span>
        </p>

        <div className="text-muted-foreground mt-6 flex flex-col gap-2 border-t pt-6 text-xs sm:flex-row sm:justify-between">
          <span>
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
          <span>The gaik package is open source under the MIT licence.</span>
        </div>
      </div>
    </footer>
  );
}

const DISCLAIMER =
  " The demo website uses Microsoft Azure APIs for OpenAI's and Anthropic's models, and Google's Vertex AI for Gemini models. No user data is retained, and neither Azure nor Vertex AI uses any user data for model training.";

function FooterColumn({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <nav aria-label={title} className="space-y-3 text-sm">
      <h2 className="text-foreground text-sm font-semibold">{title}</h2>
      <div className="flex flex-col gap-2.5">{children}</div>
    </nav>
  );
}
