"use client";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Check, ChevronDown, Copy, ExternalLink, Mail } from "lucide-react";
import { useState } from "react";

const CONTACT_EMAIL = "info@gaik.ai";
const OUTLOOK_URL = `https://outlook.office.com/mail/deeplink/compose?to=${CONTACT_EMAIL}`;
const GMAIL_URL = `https://mail.google.com/mail/?view=cm&to=${CONTACT_EMAIL}`;

/** The free PoC offer. The address opens in a mail app, a web mailer or the clipboard. */
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
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button className="shrink-0 gap-2">
            <Mail className="size-4" />
            Contact GAIK
            <ChevronDown className="size-4 opacity-70" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuItem asChild>
            <a href={`mailto:${CONTACT_EMAIL}`}>
              <Mail className="size-4" />
              Open in your mail app
            </a>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <a href={OUTLOOK_URL} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="size-4" />
              Write in Outlook on the web
            </a>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <a href={GMAIL_URL} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="size-4" />
              Write in Gmail
            </a>
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault();
              void copyEmail();
            }}
          >
            {copied ? (
              <Check className="size-4" />
            ) : (
              <Copy className="size-4" />
            )}
            {copied ? "Copied" : `Copy ${CONTACT_EMAIL}`}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </section>
  );
}
