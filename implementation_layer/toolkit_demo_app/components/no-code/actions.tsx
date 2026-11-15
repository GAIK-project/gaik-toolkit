"use client";

import { Button } from "@/components/ui/button";
import { Check, Copy } from "lucide-react";
import { useState, type ComponentProps, type ReactNode } from "react";
import toast from "react-hot-toast";

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** Copies `text` and reports `copied` for two seconds; a failure shows a toast. */
function useCopy(text: string) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!(await copyText(text))) {
      toast.error("Could not copy. Select the text and copy it by hand.");
      return;
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return { copied, copy };
}

export function CopyButton({
  text,
  label = "Copy prompt",
  variant = "outline",
}: {
  text: string;
  label?: string;
  variant?: ComponentProps<typeof Button>["variant"];
}) {
  const { copied, copy } = useCopy(text);

  return (
    <Button variant={variant} size="sm" onClick={copy}>
      {copied ? <Check /> : <Copy />}
      {copied ? "Copied" : label}
    </Button>
  );
}

/** The icon-only copy control beside a command; `label` names what it copies. */
export function CopyIconButton({
  text,
  label,
}: {
  text: string;
  label: string;
}) {
  const { copied, copy } = useCopy(text);
  const name = copied ? "Copied" : label;

  return (
    <Button
      variant="ghost"
      size="icon-lg"
      onClick={copy}
      aria-label={name}
      title={name}
      className="text-muted-foreground hover:text-foreground size-12"
    >
      {copied ? <Check className="text-primary" /> : <Copy />}
      <span className="sr-only" role="status">
        {copied ? "Copied" : ""}
      </span>
    </Button>
  );
}

/**
 * Copies the text, then opens the app in a new tab. The copy starts inside the
 * click, before the browser leaves the page, so it is not blocked as a popup.
 */
export function CopyAndOpen({
  text,
  href,
  message,
  title,
  children,
}: {
  text: string;
  href: string;
  message: string;
  title?: string;
  children: ReactNode;
}) {
  return (
    <Button variant="outline" size="sm" asChild>
      <a
        href={href}
        title={title}
        target="_blank"
        rel="noopener noreferrer"
        onClick={() => {
          void copyText(text).then((ok) => {
            if (ok) toast.success(message);
          });
        }}
      >
        {children}
      </a>
    </Button>
  );
}
