"use client";

import { useState, useEffect, useCallback } from "react";
import { createClient } from "@/lib/supabase/client";
import type { DemoType, Feedback, FeedbackFormData } from "@/lib/types";

interface UseFeedbackReturn {
  feedback: Feedback | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  saveFeedback: (data: FeedbackFormData) => Promise<boolean>;
}

const STORAGE_KEY_PREFIX = "gaik-feedback-";

function getLocalFeedback(demoType: DemoType): FeedbackFormData | null {
  if (typeof window === "undefined") return null;
  const stored = localStorage.getItem(`${STORAGE_KEY_PREFIX}${demoType}`);
  return stored ? JSON.parse(stored) : null;
}

function setLocalFeedback(demoType: DemoType, data: FeedbackFormData): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(`${STORAGE_KEY_PREFIX}${demoType}`, JSON.stringify(data));
}

export function useFeedback(demoType: DemoType): UseFeedbackReturn {
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userId, setUserId] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createClient();

    async function checkAuthAndFetchFeedback() {
      setIsLoading(true);

      const {
        data: { user },
      } = await supabase.auth.getUser();

      if (!user) {
        setIsAuthenticated(false);
        setIsLoading(false);
        return;
      }

      setIsAuthenticated(true);
      setUserId(user.id);

      const { data } = await supabase
        .from("feedback")
        .select("*")
        .eq("user_id", user.id)
        .eq("demo_type", demoType)
        .single();

      if (data) {
        setFeedback(data as Feedback);
      } else {
        // Check localStorage for pending feedback
        const local = getLocalFeedback(demoType);
        if (local) {
          setFeedback({
            id: "",
            user_id: user.id,
            demo_type: demoType,
            rating: local.rating,
            comment: local.comment || null,
            created_at: "",
            updated_at: "",
          });
        }
      }

      setIsLoading(false);
    }

    checkAuthAndFetchFeedback();
  }, [demoType]);

  const saveFeedback = useCallback(
    async (data: FeedbackFormData): Promise<boolean> => {
      if (!userId) return false;

      const supabase = createClient();

      // Save to localStorage first for persistence
      setLocalFeedback(demoType, data);

      const feedbackData = {
        user_id: userId,
        demo_type: demoType,
        rating: data.rating,
        comment: data.comment?.trim() || null,
      };

      const { data: result, error } = await supabase
        .from("feedback")
        .upsert(feedbackData, {
          onConflict: "user_id,demo_type",
        })
        .select()
        .single();

      if (error) {
        console.error("Failed to save feedback:", error);
        return false;
      }

      setFeedback(result as Feedback);
      return true;
    },
    [demoType, userId]
  );

  return {
    feedback,
    isLoading,
    isAuthenticated,
    saveFeedback,
  };
}
