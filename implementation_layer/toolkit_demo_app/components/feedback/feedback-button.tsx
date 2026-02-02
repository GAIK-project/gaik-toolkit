"use client";

import { useState } from "react";
import { Star, Pencil } from "lucide-react";
import toast from "react-hot-toast";
import { Button } from "@/components/ui/button";
import { FeedbackDialog } from "./feedback-dialog";
import { useFeedback } from "./use-feedback";
import type { DemoType, FeedbackFormData } from "@/lib/types";

interface FeedbackButtonProps {
  demoType: DemoType;
}

export function FeedbackButton({ demoType }: FeedbackButtonProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const { feedback, isLoading, isAuthenticated, saveFeedback } =
    useFeedback(demoType);

  const handleSubmit = async (data: FeedbackFormData): Promise<boolean> => {
    const success = await saveFeedback(data);
    if (success) {
      toast.success(
        feedback?.id ? "Feedback updated!" : "Thanks for your feedback!"
      );
    } else {
      toast.error("Failed to save feedback. Please try again.");
    }
    return success;
  };

  // Don't show button if not authenticated or still loading
  if (isLoading || !isAuthenticated) {
    return null;
  }

  const hasExistingFeedback = feedback?.id;

  return (
    <>
      <Button
        variant="ghost"
        size="xs"
        onClick={() => setDialogOpen(true)}
        className={
          hasExistingFeedback
            ? "text-amber-600 hover:text-amber-700 hover:bg-amber-50"
            : "text-muted-foreground hover:text-amber-600 hover:bg-amber-50"
        }
      >
        {hasExistingFeedback ? (
          <>
            <Star className="size-3 fill-amber-400 text-amber-400" />
            {feedback.rating}/5
          </>
        ) : (
          <>
            <Star className="size-3 text-amber-400" />
            Rate this
          </>
        )}
      </Button>

      <FeedbackDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        initialRating={feedback?.rating || 0}
        initialComment={feedback?.comment || ""}
        onSubmit={handleSubmit}
        isEdit={!!hasExistingFeedback}
      />
    </>
  );
}
