"use client";

import { GitHubIcon } from "@/components/github-icon";
import {
  ArrowUpRight,
  BookOpen,
  Check,
  Copy,
  type LucideIcon,
  Package,
} from "lucide-react";
import { type ComponentType, useState } from "react";

const rowClassName =
  "group bg-background/70 hover:border-primary/40 flex w-full items-center gap-3.5 rounded-xl border px-4 py-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md motion-reduce:hover:translate-y-0";

function RowContent({
  icon: Icon,
  title,
}: {
  icon: LucideIcon | ComponentType<{ className?: string }>;
  title: string;
}) {
  return (
    <>
      <span className="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg">
        <Icon className="size-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-medium">{title}</span>
      </span>
      <ArrowUpRight className="text-muted-foreground group-hover:text-primary size-4 shrink-0 transition-colors" />
    </>
  );
}

const INSTALL_COMMAND = "pip install gaik[all]";

function InstallTerminal() {
  const [copied, setCopied] = useState(false);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(INSTALL_COMMAND);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked: the command stays selectable.
    }
  }

  return (
    <div className="max-w-md overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 shadow-sm">
      <div className="flex items-center gap-3 px-4 py-3.5 font-mono text-sm">
        <span aria-hidden className="text-teal-400 select-none">
          $
        </span>
        <code className="min-w-0 flex-1 truncate text-zinc-100">
          {INSTALL_COMMAND}
        </code>
        <button
          type="button"
          onClick={copy}
          aria-label="Copy install command"
          className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
        >
          {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
        </button>
      </div>
    </div>
  );
}

const links = [
  {
    href: "https://gaik-project.github.io/gaik-toolkit/",
    icon: BookOpen,
    title: "Documentation",
  },
  {
    href: "https://pypi.org/project/gaik/",
    icon: Package,
    title: "PyPI package",
  },
  {
    href: "https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples",
    icon: GitHubIcon,
    title: "Examples on GitHub",
  },
];

/** The closing call to action: install the package or read on. The Wizard is under the hero. */
export function GetStarted() {
  return (
    <section
      id="get-started"
      className="from-primary/10 via-card to-card relative scroll-mt-24 overflow-hidden rounded-2xl border bg-gradient-to-br p-6 shadow-sm md:p-10"
    >
      <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-center">
        <div className="min-w-0 space-y-4">
          <h2 className="font-serif text-2xl font-semibold tracking-tight text-balance md:text-3xl">
            Build your own solution with GAIK
          </h2>
          <p className="text-muted-foreground max-w-xl">
            Every demo on this site runs on gaik, an open-source (MIT) Python
            package.
          </p>
          <InstallTerminal />
        </div>

        <div className="flex flex-col gap-2.5">
          {links.map(({ href, ...content }) => (
            <a
              key={href}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className={rowClassName}
            >
              <RowContent {...content} />
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
