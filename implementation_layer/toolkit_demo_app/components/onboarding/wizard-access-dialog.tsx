"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  buildAccessRequestMailto,
  GAIK_CONTACT_URL,
} from "@/lib/onboarding/mailto";
import { Mail, Wand2 } from "lucide-react";

interface WizardAccessDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Explains how to get Solution Wizard (beta) access and offers two contact
 * paths: a prefilled email to the GAIK team, plus the public contact page.
 */
export function WizardAccessDialog({
  open,
  onOpenChange,
}: WizardAccessDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="bg-primary/10 mb-1 flex size-11 items-center justify-center rounded-full">
            <Wand2 className="text-primary size-5" />
          </div>
          <DialogTitle className="font-serif text-xl">
            Solution Configuration Wizard
            <span className="bg-primary/15 text-primary ml-2 rounded-full px-2 py-0.5 align-middle text-[10px] font-semibold tracking-wide uppercase">
              Beta
            </span>
          </DialogTitle>
          <DialogDescription className="text-sm leading-relaxed">
            The Wizard turns a plain-language use case into a validated proof of
            concept. It&apos;s currently in private beta. To try it, contact the
            GAIK team with a short introduction of your company and a
            description of your use case — we&apos;ll get you set up.
          </DialogDescription>
        </DialogHeader>

        <div className="mt-2 flex flex-col gap-3">
          <Button asChild size="lg" className="gap-2">
            <a href={buildAccessRequestMailto()}>
              <Mail className="size-4" />
              Request access by email
            </a>
          </Button>
          <p className="text-muted-foreground text-center text-xs">
            or visit{" "}
            <a
              href={GAIK_CONTACT_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline"
            >
              gaik.ai/contact-info
            </a>
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
