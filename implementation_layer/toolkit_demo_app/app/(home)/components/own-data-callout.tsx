"use client";

import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Check, Copy, Mail } from "lucide-react";
import { useState } from "react";

const CONTACT_EMAIL = "info@gaik.ai";

/** The free PoC offer. Copying the address works even without a mail app. */
export function OwnDataCallout() {
  const [copied, setCopied] = useState(false);

  async function copyEmail(): Promise<void> {
    try {
      await navigator.clipboard.writeText(CONTACT_EMAIL);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked: the mailto link and the visible address still work.
    }
  }

  return (
    <section
      aria-label="Proof of concept"
      className="bg-muted/40 flex flex-col gap-4 rounded-xl border p-5 md:flex-row md:items-center md:justify-between"
    >
      <div className="space-y-1">
        <h2 className="font-serif text-xl font-semibold text-balance">
          Try it with your own data
        </h2>
        <p className="text-muted-foreground max-w-xl text-sm">
          Every demo accepts your own documents and recordings. Companies in
          Finland can get <strong>free proof-of-concept development</strong>{" "}
          from GAIK&apos;s team.
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <a
          href={`mailto:${CONTACT_EMAIL}`}
          className={cn(buttonVariants(), "gap-2")}
        >
          <Mail className="size-4" />
          {CONTACT_EMAIL}
        </a>
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={copyEmail}
          aria-label="Copy email address"
        >
          {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
        </Button>
      </div>
    </section>
  );
}
