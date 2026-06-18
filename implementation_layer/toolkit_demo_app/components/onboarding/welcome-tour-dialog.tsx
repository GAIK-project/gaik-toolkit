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
import { Compass, Sparkles } from "lucide-react";

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
          <div className="bg-primary/10 mb-1 flex size-11 items-center justify-center rounded-full">
            <Sparkles className="text-primary size-5" />
          </div>
          <DialogTitle className="font-serif text-xl">
            Welcome to the GAIK Toolkit
          </DialogTitle>
          <DialogDescription className="text-sm leading-relaxed">
            Everything here is a live, runnable demo — real use cases and the AI
            building blocks behind them. Want a quick 60-second tour of the
            highlights?
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
