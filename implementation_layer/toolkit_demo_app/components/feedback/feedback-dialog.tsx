"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { StarRating } from "./star-rating";
import type { FeedbackFormData } from "@/lib/types";

interface FeedbackDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialRating?: number;
  initialComment?: string;
  onSubmit: (data: FeedbackFormData) => Promise<boolean>;
  isEdit?: boolean;
}

const MAX_COMMENT_LENGTH = 500;

export function FeedbackDialog({
  open,
  onOpenChange,
  initialRating = 0,
  initialComment = "",
  onSubmit,
  isEdit = false,
}: FeedbackDialogProps) {
  const [rating, setRating] = useState(initialRating);
  const [comment, setComment] = useState(initialComment);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (rating === 0) return;

    setIsSubmitting(true);
    const success = await onSubmit({ rating, comment: comment || undefined });
    setIsSubmitting(false);

    if (success) {
      onOpenChange(false);
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      // Reset form when closing
      setRating(initialRating);
      setComment(initialComment);
    }
    onOpenChange(newOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit your feedback" : "Rate this demo"}
          </DialogTitle>
          <DialogDescription>
            Your feedback helps us improve. {isEdit ? "Update" : "Share"} your
            rating and any comments.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>Rating</Label>
            <StarRating
              value={rating}
              onChange={setRating}
              disabled={isSubmitting}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="comment">
              Comment{" "}
              <span className="text-muted-foreground font-normal">
                (optional)
              </span>
            </Label>
            <Textarea
              id="comment"
              placeholder="What did you think of this demo?"
              value={comment}
              onChange={(e) =>
                setComment(e.target.value.slice(0, MAX_COMMENT_LENGTH))
              }
              disabled={isSubmitting}
              rows={3}
            />
            <p className="text-xs text-muted-foreground text-right">
              {comment.length}/{MAX_COMMENT_LENGTH}
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={rating === 0 || isSubmitting}
          >
            {isSubmitting ? "Saving..." : isEdit ? "Update" : "Submit"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
