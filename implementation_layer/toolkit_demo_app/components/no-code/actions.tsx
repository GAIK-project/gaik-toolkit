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

export function CopyButton({
  text,
  label = "Copy prompt",
  variant = "outline",
}: {
  text: string;
  label?: string;
  variant?: ComponentProps<typeof Button>["variant"];
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!(await copyText(text))) {
      toast.error("Could not copy. Select the text and copy it by hand.");
      return;
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Button variant={variant} size="sm" onClick={copy}>
      {copied ? <Check /> : <Copy />}
      {copied ? "Copied" : label}
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
  children,
}: {
  text: string;
  href: string;
  message: string;
  children: ReactNode;
}) {
  return (
    <Button variant="outline" size="sm" asChild>
      <a
        href={href}
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
