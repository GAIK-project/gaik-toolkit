"use client";

import { componentSourceFor, installCommand } from "@/lib/component-sources";
import { cn } from "@/lib/utils";
import { BookOpen, Check, Copy } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

/** GitHub's mark, inline so it is drawn with the text instead of loading late. */
function GitHubMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 98 96"
      aria-hidden="true"
      className={className}
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M48.854 0C21.839 0 0 22 0 49.217c0 21.756 13.993 40.172 33.405 46.69 2.427.49 3.316-1.059 3.316-2.362 0-1.141-.08-5.052-.08-9.127-13.59 2.934-16.42-5.867-16.42-5.867-2.184-5.704-5.42-7.17-5.42-7.17-4.448-3.015.324-3.015.324-3.015 4.934.326 7.523 5.052 7.523 5.052 4.367 7.496 11.404 5.378 14.235 4.074.404-3.178 1.699-5.378 3.074-6.6-10.839-1.141-22.243-5.378-22.243-24.283 0-5.378 1.94-9.778 5.014-13.2-.485-1.222-2.184-6.275.486-13.038 0 0 4.125-1.304 13.426 5.052a46.97 46.97 0 0 1 12.214-1.63c4.125 0 8.33.571 12.213 1.63 9.302-6.356 13.427-5.052 13.427-5.052 2.67 6.763.97 11.816.485 13.038 3.155 3.422 5.015 7.822 5.015 13.2 0 18.905-11.404 23.06-22.324 24.283 1.78 1.548 3.316 4.481 3.316 9.126 0 6.6-.08 11.897-.08 13.526 0 1.304.89 2.853 3.316 2.364 19.412-6.52 33.405-24.935 33.405-46.691C97.707 22 75.788 0 48.854 0z"
      />
    </svg>
  );
}

const linkClassName =
  "text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 rounded-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

/**
 * One quiet line under a demo's title: the pip command that installs the gaik parts it
 * uses, and links to its source on GitHub and its docs. Nothing renders for a page
 * without an entry in lib/component-sources.ts.
 */
export function ComponentSource({ className }: { className?: string }) {
  const pathname = usePathname();
  const source = componentSourceFor(pathname);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  if (!source) return null;
  const command =
    source.extras.length > 0 ? installCommand(source.extras) : null;

  async function copy(): Promise<void> {
    if (!command) return;
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
    } catch {
      // Clipboard blocked: the command stays selectable.
    }
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-4 gap-y-2 text-sm",
        className,
      )}
    >
      {command && (
        <span className="bg-muted/60 inline-flex max-w-full min-w-0 items-center rounded-md border py-0.5 pr-0.5 pl-2.5">
          <code className="min-w-0 font-mono text-xs [overflow-wrap:anywhere]">
            {command}
          </code>
          <button
            type="button"
            onClick={copy}
            aria-label={copied ? "Copied" : "Copy install command"}
            title={copied ? "Copied" : "Copy install command"}
            className="text-muted-foreground hover:text-foreground hover:bg-background ml-1 grid size-7 shrink-0 place-items-center rounded-[5px] transition-[color,background-color,scale] duration-150 active:scale-90"
          >
            {copied ? (
              <Check className="animate-in zoom-in-50 size-3.5 duration-150" />
            ) : (
              <Copy className="size-3.5" />
            )}
          </button>
        </span>
      )}
      <a
        href={source.sourceUrl}
        target="_blank"
        rel="noopener noreferrer"
        className={linkClassName}
      >
        <GitHubMark className="size-4" />
        Source
      </a>
      {source.docsUrl && (
        <a
          href={source.docsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className={linkClassName}
        >
          <BookOpen className="size-4" />
          Docs
        </a>
      )}
    </div>
  );
}
