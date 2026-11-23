"use client";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  PRIVACY_LAST_UPDATED,
  PrivacyContent,
} from "@/components/privacy-content";

export function PrivacyDialog({ children }: { children: React.ReactNode }) {
  return (
    <Dialog>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="max-w-2xl gap-0 p-0">
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle className="text-lg font-semibold">
            Privacy Notice
          </DialogTitle>
          <p className="text-muted-foreground text-sm">
            GAIK Toolkit Demo — Last updated {PRIVACY_LAST_UPDATED}
          </p>
        </DialogHeader>
        <ScrollArea className="max-h-[70vh] px-6 py-5">
          <PrivacyContent />
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
