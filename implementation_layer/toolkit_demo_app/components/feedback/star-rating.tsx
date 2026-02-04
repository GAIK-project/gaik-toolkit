"use client";

import { Star } from "lucide-react";
import { cn } from "@/lib/utils";

interface StarRatingProps {
  value: number;
  onChange: (rating: number) => void;
  disabled?: boolean;
}

export function StarRating({ value, onChange, disabled }: StarRatingProps) {
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          disabled={disabled}
          onClick={() => onChange(star)}
          className={cn(
            "focus-visible:ring-ring rounded-sm p-0.5 transition-colors focus:outline-none focus-visible:ring-2",
            disabled && "cursor-not-allowed opacity-50",
          )}
          aria-label={`Rate ${star} star${star > 1 ? "s" : ""}`}
        >
          <Star
            className={cn(
              "size-6 transition-colors",
              star <= value
                ? "fill-warning text-warning"
                : "text-muted-foreground hover:text-warning",
            )}
          />
        </button>
      ))}
    </div>
  );
}
