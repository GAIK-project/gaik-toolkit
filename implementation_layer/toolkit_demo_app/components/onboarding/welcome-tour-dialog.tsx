"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Compass } from "lucide-react";

interface WelcomeTourDialogProps {
  open: boolean;
  onStart: () => void;
  onDismiss: () => void;
}

/** First-visit welcome that invites the user into the guided tour. */
export function WelcomeTourDialog({
  open,
  onStart,
  onDismiss,
}: WelcomeTourDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onDismiss();
      }}
    >
      <DialogContent className="sm:max-w-md" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="font-serif text-xl">
            Welcome to the GAIK Toolkit
          </DialogTitle>
          <DialogDescription className="text-sm leading-relaxed">
            Every demo here runs for real. A one-minute tour shows where to
            start.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="mt-2">
          <Button variant="ghost" onClick={onDismiss}>
            Maybe later
          </Button>
          <Button className="gap-2" onClick={onStart}>
            <Compass className="size-4" />
            Start tour
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
